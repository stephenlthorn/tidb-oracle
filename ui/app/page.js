import { redirect } from 'next/navigation';
import { getSession } from '../lib/session';

export default async function RootPage() {
  const session = await getSession();
  if (session?.access_token && Date.now() < session.expires_at) {
    redirect('/rep');
  }
  redirect('/login');
}
