import React, { useState } from 'react';

export function useUser() {
  const [user, setUser] = useState({ name: 'Bob' });
  return user;
}

export function UserCard({ name }: { name: string }) {
  return <div className="card">{name}</div>;
}

export function UserProfile() {
  const user = useUser();
  return (
    <section>
      <UserCard name={user.name} />
    </section>
  );
}

export default function App() {
  return (
    <main>
      <UserProfile />
    </main>
  );
}
