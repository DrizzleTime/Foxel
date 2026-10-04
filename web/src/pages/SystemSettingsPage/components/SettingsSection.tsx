import type { ReactNode } from 'react';

interface SettingsSectionProps {
  title: ReactNode;
  action?: ReactNode;
  children: ReactNode;
}

export default function SettingsSection({ title, action, children }: SettingsSectionProps) {
  return (
    <section className="fx-settings-section fx-settings-group">
      <div className="fx-settings-section-heading">
        <h3>{title}</h3>
        {action && <div className="fx-settings-section-action">{action}</div>}
      </div>
      {children}
    </section>
  );
}
