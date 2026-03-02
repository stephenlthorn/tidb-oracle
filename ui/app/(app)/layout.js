import { getSession } from '../../lib/session';
import Sidebar from '../../components/Sidebar';

export default async function AppLayout({ children }) {
  const session = await getSession();
  const email = session?.email || 'oracle@pingcap.com';
  const hasSession = Boolean(session?.access_token);

  return (
    <div className="shell">
      <Sidebar email={email} hasSession={hasSession} />
      <div className="main">
        <div className="internal-reminder">
          Internal only - do not share outside PingCAP.
        </div>
        {children}
      </div>
    </div>
  );
}
