import { redirect } from 'next/navigation';
import { getSession } from '../../lib/session';
import Sidebar from '../../components/Sidebar';

export default async function AppLayout({ children }) {
  const session = await getSession();
  if (!session?.access_token) redirect('/login');

  return (
    <div className="shell">
      <Sidebar email={session.email} />
      <div className="main">{children}</div>
    </div>
  );
}
