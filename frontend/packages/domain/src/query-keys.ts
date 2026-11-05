// 查询键工厂：失效缓存时按键精确失效（实现文档第 8 节）
export const qk = {
  workbench: {
    summary: () => ['workbench', 'summary'] as const,
    cards: (filters?: Record<string, unknown>) => ['workbench', 'cards', filters ?? {}] as const,
    activity: () => ['workbench', 'activity'] as const,
    health: () => ['workbench', 'health'] as const,
    handoffs: () => ['workbench', 'handoffs'] as const,
    anomalies: () => ['workbench', 'anomalies'] as const,
  },
  candidate: {
    list: (filters?: Record<string, unknown>) => ['candidate', 'list', filters ?? {}] as const,
    detail: (id: string) => ['candidate', id] as const,
    applications: (id: string) => ['candidate', id, 'applications'] as const,
    resume: (id: string) => ['candidate', id, 'resume'] as const,
    conversation: (id: string) => ['candidate', id, 'conversation'] as const,
    logs: (id: string) => ['candidate', id, 'logs'] as const,
  },
  evaluation: (applicationId: string) => ['evaluation', applicationId] as const,
  position: {
    list: (filters?: Record<string, unknown>) => ['position', 'list', filters ?? {}] as const,
    detail: (id: string) => ['position', id] as const,
    funnel: (id: string) => ['position', id, 'funnel'] as const,
    profile: (id: string) => ['position', id, 'profile'] as const,
    kb: (id: string) => ['position', id, 'kb'] as const,
    applications: (id: string) => ['position', id, 'applications'] as const,
  },
  requisition: {
    list: (filters?: Record<string, unknown>) => ['requisition', 'list', filters ?? {}] as const,
    detail: (id: string) => ['requisition', id] as const,
  },
  interview: { list: (filters?: Record<string, unknown>) => ['interview', 'list', filters ?? {}] as const },
  settings: { automation: () => ['settings', 'automation'] as const },
  biz: { inbox: () => ['biz', 'inbox'] as const, brief: (appId: string) => ['biz', 'brief', appId] as const },
  candidatePortal: {
    session: () => ['portal', 'session'] as const,
    messages: () => ['portal', 'messages'] as const,
    slots: () => ['portal', 'slots'] as const,
  },
};
