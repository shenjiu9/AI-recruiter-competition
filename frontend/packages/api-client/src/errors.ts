// 统一错误：后端错误格式见实现文档第 9 节 { error: { code, message, details, trace_id } }
export class AppError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status = 500,
    public readonly details?: Record<string, unknown>,
    public readonly traceId?: string,
  ) {
    super(message);
    this.name = 'AppError';
  }
}

export function toAppError(e: unknown): AppError {
  if (e instanceof AppError) return e;
  if (e instanceof TypeError) return new AppError('NETWORK', '网络连接失败，请检查网络后重试', 0);
  return new AppError('UNKNOWN', e instanceof Error ? e.message : '出现未知错误', 500);
}

/** 409 版本冲突：前端弹 ConflictDialog */
export const isConflict = (e: unknown): boolean => e instanceof AppError && e.code === 'VERSION_CONFLICT';
export const isAiDegraded = (e: unknown): boolean => e instanceof AppError && e.code === 'AI_DEGRADED';
