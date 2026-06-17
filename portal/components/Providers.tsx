'use client';

import { SWRConfig } from 'swr';

export default function Providers({ children }: { children: React.ReactNode }) {
  return (
    <SWRConfig
      value={{
        revalidateOnFocus: false,
        errorRetryCount: 2,
        onError: (error: Error) => {
          // Phase 21 — both access and refresh tokens are gone (BFF couldn't
          // refresh); send the browser back to the login page rather than
          // leaving every panel stuck on a raw 401.
          if (typeof window !== 'undefined' && /→ 401/.test(error?.message || '')) {
            window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
          }
        },
      }}
    >
      {children}
    </SWRConfig>
  );
}
