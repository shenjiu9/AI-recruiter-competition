import { Button } from 'antd';
import type { ButtonHTMLAttributes } from 'react';

/** Preserve HTML form behavior while sharing the Ant Design button theme. */
export function ActionButton({
  type = 'submit',
  className = '',
  ...props
}: Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'color'>) {
  return <Button {...props} htmlType={type} className={`rc-action ${className}`} />;
}
