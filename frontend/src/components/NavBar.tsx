import { ChartBar, Gear, House, ListDashes, ShieldCheck } from "@phosphor-icons/react";
import { NavLink } from "react-router-dom";

const navItems = [
  { to: "/", label: "Executive Overview", icon: House, testId: "nav-executive-overview-link" },
  { to: "/integrations", label: "Integrations", icon: ListDashes, testId: "nav-integrations-link" },
  { to: "/settings", label: "Settings", icon: Gear, testId: "nav-settings-link" },
  { to: "/security", label: "Security", icon: ShieldCheck, testId: "nav-security-link" },
];

export const NavBar = () => {
  return (
    <header className="top-nav" data-testid="top-navigation">
      <div className="brand" data-testid="brand-title">
        <ChartBar size={24} weight="duotone" />
        <div>
          <h1 className="brand-title">badger-oic-monitor</h1>
          <p className="brand-subtitle" data-testid="brand-subtitle">
            Badger Oracle Integration Cloud Monitoring
          </p>
        </div>
      </div>
      <nav className="nav-links" data-testid="main-nav-links">
        {navItems.map(({ to, label, icon: Icon, testId }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
            data-testid={testId}
          >
            <Icon size={18} /> {label}
          </NavLink>
        ))}
      </nav>
    </header>
  );
};
