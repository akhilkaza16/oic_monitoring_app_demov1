import { FormEvent } from "react";

interface FirstAdminSetupPanelProps {
  registerEmail: string;
  registerPassword: string;
  status: string;
  onRegisterEmailChange: (value: string) => void;
  onRegisterPasswordChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
}

interface AdminLoginPanelProps {
  loginEmail: string;
  loginPassword: string;
  status: string;
  onLoginEmailChange: (value: string) => void;
  onLoginPasswordChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
}

export const FirstAdminSetupPanel = ({
  registerEmail,
  registerPassword,
  status,
  onRegisterEmailChange,
  onRegisterPasswordChange,
  onSubmit,
}: FirstAdminSetupPanelProps) => {
  return (
    <form className="card auth-card" onSubmit={onSubmit} data-testid="settings-register-form">
      <label className="field">
        <span data-testid="settings-register-email-label">Admin Email</span>
        <input
          type="email"
          value={registerEmail}
          onChange={(event) => onRegisterEmailChange(event.target.value)}
          data-testid="settings-register-email-input"
        />
      </label>
      <label className="field">
        <span data-testid="settings-register-password-label">Password</span>
        <input
          type="password"
          value={registerPassword}
          onChange={(event) => onRegisterPasswordChange(event.target.value)}
          minLength={8}
          data-testid="settings-register-password-input"
        />
      </label>
      <button type="submit" className="button-primary" data-testid="settings-register-submit-button">
        Create Admin
      </button>
      <p className="muted" data-testid="settings-register-status-message">
        {status}
      </p>
    </form>
  );
};

export const AdminLoginPanel = ({
  loginEmail,
  loginPassword,
  status,
  onLoginEmailChange,
  onLoginPasswordChange,
  onSubmit,
}: AdminLoginPanelProps) => {
  return (
    <form className="card auth-card" onSubmit={onSubmit} data-testid="settings-login-form">
      <label className="field">
        <span data-testid="settings-login-email-label">Email</span>
        <input
          type="email"
          value={loginEmail}
          onChange={(event) => onLoginEmailChange(event.target.value)}
          data-testid="settings-login-email-input"
        />
      </label>
      <label className="field">
        <span data-testid="settings-login-password-label">Password</span>
        <input
          type="password"
          value={loginPassword}
          onChange={(event) => onLoginPasswordChange(event.target.value)}
          minLength={8}
          data-testid="settings-login-password-input"
        />
      </label>
      <button type="submit" className="button-primary" data-testid="settings-login-submit-button">
        Sign In
      </button>
      <p className="muted" data-testid="settings-login-status-message">
        {status}
      </p>
    </form>
  );
};
