import { defineConfig } from '@playwright/test';
import prototypeConfig from './playwright.config';

// Preserve the historical config/test inputs. This separately runs the same
// browser assertions against the migrated production API fixture.
const servers = Array.isArray(prototypeConfig.webServer) ? prototypeConfig.webServer : [];
export default defineConfig({
  ...prototypeConfig,
  testMatch: 'controls.spec.ts',
  webServer: servers.map(server => ({
    ...server,
    command: server.command.replace(
      '../docs/admin/implementation/batch11-issue-611-evidence/browser_api.py',
      '../backend/tests/admin_audit_epoch/browser_api.py',
    ),
  })),
});
