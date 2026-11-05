// 埋点（PRD 21.2）。不含候选人姓名、联系方式，只用对象 id。
import { useEffect } from 'react';

export type TrackEvent =
  | 'wb_card_action'
  | 'wb_spotcheck'
  | 'conv_takeover'
  | 'conv_handback'
  | 'rq_create_start'
  | 'rq_ai_fill'
  | 'rq_field_edit'
  | 'rq_pending_answer'
  | 'rq_submit'
  | 'cd_detail_view'
  | 'cd_app_switch'
  | 'jb_stage_click'
  | 'iv_feedback_submit'
  | 'im_card_action'
  | 'ai_fallback'
  | 'ex_consent'
  | 'ex_slot_select'
  | 'page_view';

export type TrackProps = Record<string, string | number | boolean | undefined>;

type Sink = (event: TrackEvent, props: TrackProps) => void;
let sink: Sink = (event, props) => {
  if (import.meta.env?.DEV) console.debug('[track]', event, props);
};

export const setTrackSink = (s: Sink) => {
  sink = s;
};

export function track(event: TrackEvent, props: TrackProps = {}): void {
  sink(event, { ...props, at: Date.now() });
}

export function usePageView(pageId: string): void {
  useEffect(() => {
    track('page_view', { page: pageId });
  }, [pageId]);
}
