"""Bounded document extraction; originals never become evaluation input."""

import json
import re
import subprocess
import sys
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

from app.kernel.types import DomainError
from app.modules.candidate.contracts import Profile

MAX_FILE = 20 * 1024 * 1024
PROTECTED = re.compile(
    r"年龄|性别|婚[姻育]|已婚|未婚|民族|政治面貌|身份证|宗教|健康|出生|怀孕|孕妇|\b(?:gender|sex|age|marital|ethnicity|religion|birth)\b|(?<!\d)\d{17}[\dXx](?!\d)",
    re.I,
)


def safe_text(value):
    return "\n".join(line for line in value.splitlines() if not PROTECTED.search(line))


def validate_file(filename, data):
    if not data or len(data) > MAX_FILE:
        raise DomainError("FILE_SIZE", "简历必须非空且不超过 20 MB")
    suffix = Path(filename).suffix.lower()
    signatures = {
        ".pdf": b"%PDF-",
        ".docx": b"PK\x03\x04",
        ".doc": b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",
        ".png": b"\x89PNG\r\n\x1a\n",
        ".jpg": b"\xff\xd8\xff",
        ".jpeg": b"\xff\xd8\xff",
    }
    if suffix not in signatures or not data.startswith(signatures[suffix]):
        raise DomainError("FILE_TYPE", "请上传内容与扩展名一致的 PDF、Word、PNG 或 JPEG 简历")
    return suffix


def extract(data, suffix):
    if suffix == ".docx":
        with ZipFile(BytesIO(data)) as archive:
            if (
                len(archive.infolist()) > 1000
                or sum(i.file_size for i in archive.infolist()) > 20 * 1024 * 1024
            ):
                raise ValueError("expanded document too large")
            xml = archive.read("word/document.xml")
            if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
                raise ValueError("entities forbidden")
            root = ElementTree.fromstring(xml)
            ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            return "\n".join("".join(p.itertext()) for p in root.iter(ns + "p"))[:100000]
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(data), strict=True)
        if reader.is_encrypted or len(reader.pages) > 50:
            raise ValueError("encrypted or excessive pages")
        parts = []
        for page in reader.pages:
            content = page.get_contents()
            if content and len(content.get_data()) > 5 * 1024 * 1024:
                raise ValueError("excessive page stream")
            parts.append(page.extract_text()[:100000])
            if sum(map(len, parts)) > 100000:
                break
        return "\n".join(parts)[:100000]
    return ""  # Image/OLE Word requires OCR/conversion; human completion is explicit.


def parse_resume(filename, data):
    suffix = validate_file(filename, data)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "app.modules.candidate.parser", suffix],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=12,
            check=True,
        )
        text = json.loads(result.stdout)["text"]
    except (subprocess.SubprocessError, ValueError, KeyError):
        return {
            "profile": Profile(name="待补全").model_dump(),
            "status": "failed",
            "paragraphs": [],
            "warning": "解析失败，请下载原件核对并手动补全",
        }
    fields = {}
    labels = {
        "姓名": "name",
        "手机": "phone",
        "电话": "phone",
        "邮箱": "email",
        "城市": "city",
        "公司": "company",
        "职位": "title",
        "学校": "school",
        "学历": "degree",
        "技能": "skills",
        "工作经历": "experience",
        "教育经历": "education",
        "证书": "certificates",
        "期望城市": "expected_city",
        "期望薪资": "expected_salary",
    }
    clean = safe_text(text)
    for line in clean.splitlines():
        match = re.match(r"^\s*([^:：]+)[:：]\s*(.+)$", line)
        if match and match[1].strip() in labels:
            fields[labels[match[1].strip()]] = match[2].strip()
    for key, pattern in (
        ("phone", r"(?<!\d)(?:\+86[- ]?)?1[3-9]\d{9}(?!\d)"),
        ("email", r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"),
    ):
        if key not in fields and (match := re.search(pattern, clean)):
            fields[key] = match[0]
    fields.setdefault("name", "待补全")
    try:
        profile = Profile(**fields).model_dump()
    except ValueError:
        profile = Profile(name="待补全").model_dump()
    status = (
        "ok"
        if profile["name"] != "待补全" and (profile["phone"] or profile["email"])
        else "partial"
    )
    return {
        "profile": profile,
        "status": status,
        "paragraphs": [
            {"id": f"R{i + 1}", "text": line[:2000]}
            for i, line in enumerate(clean.splitlines()[:500])
            if line.strip()
        ],
        "warning": "自动提取供核对，原件仅供获授权 HR 查阅"
        if text
        else "图片、扫描件或旧版 Word 待人工补全；尚未接入 OCR",
    }


if __name__ == "__main__":
    # Linux worker memory budget; Windows still isolates extraction with a timeout.
    if sys.platform != "win32":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    print(json.dumps({"text": extract(sys.stdin.buffer.read(MAX_FILE + 1), sys.argv[1])}))
