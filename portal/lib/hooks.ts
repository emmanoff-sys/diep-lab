'use client';

import useSWR from 'swr';
import { getJSON } from './api';

// Polling wrapper — the backend has no push channel, so the portal polls.
// Pass null as path to conditionally skip a request (SWR convention).
export function usePolling<T>(path: string | null, intervalMs = 8000) {
  return useSWR<T>(path, getJSON, {
    refreshInterval: intervalMs,
    revalidateOnFocus: false,
    keepPreviousData: true,
  });
}
