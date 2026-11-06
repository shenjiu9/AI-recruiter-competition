import { App as AntApp, ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { useEffect, useState, type ReactNode } from 'react';
import { antdThemeConfig, type Mode } from './tokens';
import '../styles.css';
import '../workspace.css';

function preferredMode(): Mode {
  const forced = new URLSearchParams(globalThis.location?.search ?? '').get('theme');
  if (forced === 'dark' || forced === 'light') return forced;
  return globalThis.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

/** 全局主题：antd token + CSS 变量（data-theme）+ 中文语言包 */
export function RecruiterTheme({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<Mode>(preferredMode);
  useEffect(() => {
    const mq = globalThis.matchMedia?.('(prefers-color-scheme: dark)');
    const onChange = () => setMode(preferredMode());
    mq?.addEventListener('change', onChange);
    return () => mq?.removeEventListener('change', onChange);
  }, []);
  useEffect(() => {
    document.documentElement.dataset.theme = mode;
  }, [mode]);
  return (
    <ConfigProvider theme={antdThemeConfig(mode)} locale={zhCN} button={{ autoInsertSpace: false }}>
      <AntApp>{children}</AntApp>
    </ConfigProvider>
  );
}
