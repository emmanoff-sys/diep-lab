'use client';

import { useState } from 'react';
import { postJSON } from '@/lib/api';
import { ALLOWED_COMMANDS } from '@/lib/types';

export default function CommandModal({
  deviceId,
  deviceType,
  onClose,
}: {
  deviceId: string;
  deviceType: string;
  onClose: () => void;
}) {
  const commands = ALLOWED_COMMANDS[deviceType] || [];
  const [commandType, setCommandType] = useState(commands[0] || '');
  const [paramsText, setParamsText] = useState('{}');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    setResult(null);
    let params: any = {};
    try {
      params = paramsText.trim() ? JSON.parse(paramsText) : {};
    } catch {
      setError('Params must be valid JSON');
      setBusy(false);
      return;
    }
    try {
      const res: any = await postJSON('/commands', {
        device_id: deviceId,
        command_type: commandType,
        params,
        issued_by: 'portal',
      });
      setResult(`${res.status} — ${res.command_id}`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-[#161b22] border border-[#232a33] rounded-lg p-5 w-[420px] max-w-[90vw]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold">Command · {deviceId}</h3>
          <button onClick={onClose} className="text-[#8b95a1] hover:text-white">✕</button>
        </div>
        <div className="text-xs text-[#8b95a1] mb-3">{deviceType}</div>

        {commands.length === 0 ? (
          <div className="text-sm text-[#8b95a1]">No command vocabulary for this device type.</div>
        ) : (
          <>
            <label className="block text-xs text-[#8b95a1] mb-1">Command</label>
            <select
              value={commandType}
              onChange={(e) => setCommandType(e.target.value)}
              className="w-full bg-[#0f1419] border border-[#232a33] rounded px-2 py-1.5 text-sm mb-3"
            >
              {commands.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>

            <label className="block text-xs text-[#8b95a1] mb-1">Params (JSON)</label>
            <textarea
              value={paramsText}
              onChange={(e) => setParamsText(e.target.value)}
              rows={3}
              className="w-full bg-[#0f1419] border border-[#232a33] rounded px-2 py-1.5 text-sm font-mono mb-3"
            />

            <button
              onClick={submit}
              disabled={busy}
              className="bg-[#2563eb] hover:bg-[#1d4ed8] disabled:opacity-50 text-white text-sm rounded px-4 py-1.5"
            >
              {busy ? 'Sending…' : 'Send command'}
            </button>
          </>
        )}

        {result && <div className="text-[#4ade80] text-sm mt-3">Sent: {result}</div>}
        {error && <div className="text-[#f87171] text-sm mt-3">{error}</div>}
      </div>
    </div>
  );
}
