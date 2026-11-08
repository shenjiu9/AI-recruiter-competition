# AI Recruiter — submission notes

Team: NeuroMakers. Event: Vultr Agent Rush, November 2026. Track: C2, Powering the Future of Work.

## Demo route

1. Open the HR workspace and inspect the recruiting workbench.
2. Open the synthetic Python position. Its requirement is Python backend development experience.
3. Ask the assistant how many people the position still needs. The answer comes from application records.
4. Inspect the existing A2 matching result. A synthetic profile with explicit Python backend and integration-test experience has supporting evidence. Profiles without sufficient evidence receive follow-up questions rather than automatic rejection.
5. Expand the input/source evidence and inspect the human review controls. The selected matching job is still awaiting review; viewing it does not hire, reject or contact anyone.
6. Open the source hiring request and inspect the completed approval trail and generated position.

The video is an English-narrated walkthrough made from captures of the deployed Chinese-language UI. Screens use synthetic records. It includes explanatory slides, and it is not an uninterrupted real-time recording or a performance benchmark.

## Architecture and boundaries

The Vultr VM hosts Dockerized web/API services, PostgreSQL, Redis and self-hosted Dify. DeepSeek is the external model provider. The FastAPI domain layer owns business execution and validates model output. A model draft is not an approval.

Public repository contents exclude secrets and operational backups. The development login gate remains enabled. Candidate portal links are scoped, signed invitations. Do not publish credentials for the server, Dify administration, model provider or databases.

The deployment snapshot is `ec8b830`; this submission branch adds documentation without deploying new application code. Main includes newer work with identified review findings. The submitted demo makes no claim that those tools are already running or approved.

External Feishu/calendar, Tencent Meeting, SMS/email and recruitment-channel credentials are not configured. The internal workflow and adapter interfaces exist, but we do not claim real external delivery. Large-scale production performance and hiring fairness outcomes have not been established by this competition prototype.

## Materials

The submission includes a cover image, English project description, a PDF presentation, a narrated MP4 walkthrough, public repository URL and deployed application URL. The project presentation explains the intended coordination benefit; it does not invent customer counts, savings or hiring ROI.
