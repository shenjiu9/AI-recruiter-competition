// 设计 token。浅色变量同步 workspace.css，深色基础变量在 styles.css。
import { theme as antdTheme, type ThemeConfig } from 'antd';

export type Mode = 'light' | 'dark';

export const palette = {
  light: {
    ink: '#20343B',
    ink2: '#52656B',
    ink3: '#75878D',
    paper: '#F3F6F6',
    surface: '#FFFFFF',
    surface2: '#F0F5F4',
    line: '#E2EAE8',
    lineStrong: '#CDDBD7',
    brand: '#16776B',
    brandHover: '#105E55',
    brandSoft: '#E6F3EF',
    evidence: 'rgba(245, 215, 110, 0.55)',
    evidenceEdge: '#C9A227',
    ai: '#16776B',
    aiSoft: '#E7F5F0',
    ok: '#2E7D4F',
    okSoft: '#E5F2EA',
    warn: '#A86200',
    warnSoft: '#FBF0DF',
    bad: '#B3362F',
    badSoft: '#F8E5E3',
  },
  dark: {
    ink: '#E6EAF0',
    ink2: '#B8C0CC',
    ink3: '#8E98A6',
    paper: '#13171D',
    surface: '#1B2129',
    surface2: '#232A34',
    line: '#2C3440',
    lineStrong: '#46505E',
    brand: '#8FA8D9',
    brandHover: '#A9BEE6',
    brandSoft: '#1F2C44',
    evidence: 'rgba(214, 181, 72, 0.32)',
    evidenceEdge: '#D6B548',
    ai: '#6FC3CC',
    aiSoft: '#17323A',
    ok: '#6BC28D',
    okSoft: '#173024',
    warn: '#E0A94F',
    warnSoft: '#33270F',
    bad: '#EE8A82',
    badSoft: '#3A1E1C',
  },
} as const;

export const fontFamily =
  '"HarmonyOS Sans SC", "HarmonyOS Sans", "PingFang SC", "Microsoft YaHei", "Noto Sans SC", system-ui, sans-serif';

/** antd ConfigProvider 主题：视觉个性通过 token 实现，不改组件源码 */
export function antdThemeConfig(mode: Mode): ThemeConfig {
  const p = palette[mode];
  return {
    algorithm: mode === 'dark' ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
    token: {
      colorPrimary: p.brand,
      colorInfo: p.brand,
      colorSuccess: p.ok,
      colorWarning: p.warn,
      colorError: p.bad,
      colorText: p.ink,
      colorTextSecondary: p.ink2,
      colorTextTertiary: p.ink3,
      colorBgLayout: p.paper,
      colorBgContainer: p.surface,
      colorBorder: p.lineStrong,
      colorBorderSecondary: p.line,
      colorLink: p.brand,
      fontFamily,
      fontSize: 14,
      lineHeight: 1.6,
      borderRadius: 10, // 标签、输入框、按钮
      borderRadiusLG: 16, // 面板、决策卡
      borderRadiusXS: 6,
      controlHeight: 40,
      boxShadow: '0 1px 2px rgba(28, 37, 51, 0.06), 0 2px 8px rgba(28, 37, 51, 0.06)',
      boxShadowSecondary: '0 8px 24px rgba(28, 37, 51, 0.14)',
      motionDurationMid: '0.16s',
      motionEaseOut: 'cubic-bezier(0.2, 0, 0, 1)',
      fontWeightStrong: 600,
    },
    components: {
      Layout: {
        headerBg: p.surface,
        siderBg: p.surface,
        bodyBg: p.paper,
        headerHeight: 56,
        headerPadding: '0 24px',
      },
      Menu: {
        itemSelectedBg: p.brandSoft,
        itemSelectedColor: p.brand,
        itemBorderRadius: 10,
        itemHeight: 40,
        activeBarBorderWidth: 0,
      },
      Card: { borderRadiusLG: 16, paddingLG: 24 },
      Modal: { borderRadiusLG: 12 },
      Drawer: { borderRadiusLG: 12 },
      Tabs: {
        itemSelectedColor: p.brand,
        inkBarColor: p.brand,
        horizontalItemPadding: '10px 16px',
      },
      Table: {
        headerBg: p.surface,
        headerColor: p.ink2,
        rowSelectedBg: p.brandSoft,
        borderColor: p.line,
      },
      Tag: { defaultBg: p.surface2, defaultColor: p.ink2 },
      Button: {
        primaryShadow: '0 3px 8px rgba(22, 119, 107, 0.12)',
        defaultShadow: 'none',
        dangerShadow: 'none',
        fontWeight: 400,
      },
    },
  };
}
