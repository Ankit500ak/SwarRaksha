import { useCallback, useEffect, useRef, useState } from "react";
import { api, hasToken, setToken, type CheckResult, type Circle, type Voiceprint, type AlertItem } from "./api";
import { t, type Lang } from "./i18n";
import { WavRecorder } from "./recorder";

type Tab = "home" | "live" | "enroll" | "family" | "history" | "settings";

const VERDICT_EMOJI = { green: "🟢", yellow: "🟡", red: "🔴" } as const;

export default function App() {
  const [authed, setAuthed] = useState(hasToken());
  const [lang, setLang] = useState<Lang>("en");
  const [tab, setTab] = useState<Tab>("home");
  const [voiceprints, setVoiceprints] = useState<Voiceprint[]>([]);

  const refreshVps = useCallback(async () => {
    try { setVoiceprints(await api.listVoiceprints()); } catch { /* signed out */ }
  }, []);

  useEffect(() => {
    if (authed) {
      refreshVps();
      api.me().then((u) => setLang((u.language as Lang) || "en")).catch(() => {});
    }
  }, [authed, refreshVps]);

  if (!authed) return <Landing onLogin={() => setAuthed(true)} lang={lang} />;

  return (
    <div className="shell">
      <header>
        <div className="brand">🛡️ SwarRaksha</div>
        <div className="tagline">{t("tagline", lang)}</div>
      </header>
      <nav>
        {(["home", "live", "enroll", "family", "history", "settings"] as Tab[]).map((k) => (
          <button key={k} className={tab === k ? "active" : ""} onClick={() => setTab(k)}>
            {t(k === "home" ? "checkRecording" : k === "live" ? "liveCheck" : k === "enroll" ? "enroll" : k, lang)}
          </button>
        ))}
      </nav>
      <main>
        {tab === "home" && <CheckScreen lang={lang} voiceprints={voiceprints} />}
        {tab === "live" && <LiveScreen lang={lang} voiceprints={voiceprints} />}
        {tab === "enroll" && <EnrollScreen onChange={refreshVps} voiceprints={voiceprints} />}
        {tab === "family" && <FamilyScreen />}
        {tab === "history" && <HistoryScreen lang={lang} />}
        {tab === "settings" && (
          <SettingsScreen lang={lang} onLang={async (l) => { setLang(l); try { await api.updateMe({ language: l }); } catch { /* offline */ } }}
            onLogout={() => { setToken(null); setAuthed(false); }} />
        )}
      </main>
      <footer>Baseline demo build — the detector is an untrained heuristic (see MODEL_CARD). Risk, never certainty.</footer>
    </div>
  );
}

/* ------------------------------------------------------------------ */
function Landing({ onLogin, lang }: { onLogin: () => void; lang: Lang }) {
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [stage, setStage] = useState<"email" | "code">("email");
  const [msg, setMsg] = useState("");
  return (
    <div className="shell">
      <header><div className="brand">🛡️ SwarRaksha</div><div className="tagline">{t("tagline", lang)}</div></header>
      <main>
        <section className="card hero">
          <h1>Is that really your son on the phone?</h1>
          <p>Scammers clone a family member's voice from a few seconds of audio and call in a panic:
             “Maa, I'm in trouble, send money.” SwarRaksha listens for the signs of a computer-made
             voice that human ears miss, checks the caller against your family's enrolled voices,
             and gives one clear answer.</p>
          <div className="hero-verdicts"><span>🟢 Verified</span><span>🟡 Be careful</span><span>🔴 Likely cloned</span></div>
        </section>
        <section className="card">
          <h2>Sign in</h2>
          {stage === "email" ? (
            <>
              <input placeholder="you@example.com" value={email} onChange={(e) => setEmail(e.target.value)} />
              <input placeholder="Your name (optional)" value={name} onChange={(e) => setName(e.target.value)} />
              <button className="primary" onClick={async () => {
                try { await api.requestOtp(email); setStage("code"); setMsg("Code sent. In this local dev build, the code is printed in the API server log."); }
                catch (e: any) { setMsg(e.message); }
              }}>Email me a sign-in code</button>
            </>
          ) : (
            <>
              <input placeholder="6-digit code" value={code} onChange={(e) => setCode(e.target.value)} />
              <button className="primary" onClick={async () => {
                try { const r = await api.verifyOtp(email, code, name || undefined); setToken(r.token); onLogin(); }
                catch (e: any) { setMsg(e.message); }
              }}>Verify & sign in</button>
            </>
          )}
          {msg && <p className="note">{msg}</p>}
        </section>
      </main>
    </div>
  );
}

/* ------------------------------------------------------------------ */
function useRecorder() {
  const recRef = useRef<WavRecorder | null>(null);
  const [recording, setRecording] = useState(false);
  const start = async () => { recRef.current = new WavRecorder(); await recRef.current.start(); setRecording(true); };
  const stop = async (): Promise<Blob | null> => {
    if (!recRef.current) return null;
    const blob = recRef.current.snapshotWav();
    await recRef.current.stop(); recRef.current = null; setRecording(false);
    return blob;
  };
  return { recRef, recording, start, stop };
}

function VerdictView({ result, lang }: { result: CheckResult; lang: Lang }) {
  const v = result.verdict || "yellow";
  const [challenge, setChallenge] = useState<string | null>(null);
  const [reported, setReported] = useState(false);
  const title = v === "green" ? t("verified", lang) : v === "red" ? t("cloned", lang) : t("unverified", lang);
  const advice = v === "green" ? t("greenAdvice", lang) : v === "red" ? t("redAdvice", lang) : t("yellowAdvice", lang);
  return (
    <section className={`card verdict ${v}`}>
      <div className="verdict-emoji">{VERDICT_EMOJI[v]}</div>
      <h2 className="verdict-title">{title}</h2>
      <div className="meter"><div className="meter-fill" style={{ width: `${Math.round((result.risk_score ?? 0) * 100)}%` }} /></div>
      <p className="note">{t("riskMeter", lang)}: {Math.round((result.risk_score ?? 0) * 100)}%
        {result.voiceprint_similarity != null && <> · Voice match: {Math.round(result.voiceprint_similarity * 100)}%</>}</p>
      <h3>{t("whyTitle", lang)}</h3>
      <ul>{result.reasons.map((r, i) => <li key={i}>{r.text}</li>)}</ul>
      <h3>{t("whatNext", lang)}</h3>
      <p>{advice}</p>
      <div className="windows">
        {result.windows.map((w) => (
          <div key={w.index} className="win" title={`${w.t_start.toFixed(0)}s`}>
            <div className="win-fill" style={{ height: `${Math.round((w.spoof_score ?? 0) * 100)}%` }} />
          </div>
        ))}
      </div>
      <p className="note">Each bar = 4 seconds of audio; taller = more computer-made sounding.</p>
      <div className="row">
        <button onClick={async () => { const c = await api.challenge(result.id, "code_word"); setChallenge(c.prompt); }}>
          Ask for the family code word</button>
        <button onClick={async () => { const c = await api.challenge(result.id, "liveness_phrase"); setChallenge(c.prompt); }}>
          Give a liveness phrase</button>
        <button disabled={reported} onClick={async () => { await api.report(result.id, "Reported from verdict screen"); setReported(true); }}>
          {reported ? "Reported ✓" : t("report", lang)}</button>
      </div>
      {challenge && (
        <div className="challenge">
          <p><strong>{challenge}</strong></p>
          <div className="row">
            <button className="primary" onClick={async () => { await api.challengeVerify(result.id, true); setChallenge(null); }}>They passed ✓</button>
            <button className="danger" onClick={async () => { await api.challengeVerify(result.id, false); setChallenge(null); }}>They failed ✗</button>
          </div>
          <p className="note">After answering, reopen this check from History to see the updated verdict.</p>
        </div>
      )}
    </section>
  );
}

/* ------------------------------------------------------------------ */
function CheckScreen({ lang, voiceprints }: { lang: Lang; voiceprints: Voiceprint[] }) {
  const [vpId, setVpId] = useState<number | null>(null);
  const [file, setFile] = useState<Blob | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [result, setResult] = useState<CheckResult | null>(null);
  const rec = useRecorder();

  const run = async (audio: Blob) => {
    setBusy(true); setErr(""); setResult(null);
    try { setResult(await api.checkClip(audio, vpId)); }
    catch (e: any) { setErr(e.message); }
    setBusy(false);
  };

  return (
    <>
      <section className="card">
        <h2>{t("checkRecording", lang)}</h2>
        <label>Whose voice should this be? (optional)</label>
        <select value={vpId ?? ""} onChange={(e) => setVpId(e.target.value ? Number(e.target.value) : null)}>
          <option value="">No enrolled voice — check only for a fake voice</option>
          {voiceprints.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
        </select>
        <label>Upload a recording (audio file, up to ~2 min)</label>
        <input type="file" accept="audio/*" onChange={(e) => setFile(e.target.files?.[0] || null)} />
        <div className="row">
          <button className="primary" disabled={!file || busy} onClick={() => file && run(file)}>Check this recording</button>
          {!rec.recording
            ? <button onClick={rec.start}>🎙 Record instead</button>
            : <button className="danger" onClick={async () => { const b = await rec.stop(); if (b) run(b); }}>⏹ Stop & check</button>}
        </div>
        {busy && <p className="note">{t("analysing", lang)}</p>}
        {err && <p className="error">{err}</p>}
      </section>
      {result && <VerdictView result={result} lang={lang} />}
    </>
  );
}

/* ------------------------------------------------------------------ */
function LiveScreen({ lang, voiceprints }: { lang: Lang; voiceprints: Voiceprint[] }) {
  const [vpId, setVpId] = useState<number | null>(null);
  const [checkId, setCheckId] = useState<number | null>(null);
  const [risk, setRisk] = useState<number | null>(null);
  const [verdict, setVerdict] = useState<string | null>(null);
  const [chunks, setChunks] = useState(0);
  const [final, setFinal] = useState<CheckResult | null>(null);
  const [err, setErr] = useState("");
  const rec = useRecorder();
  const timer = useRef<number | null>(null);

  const begin = async () => {
    setErr(""); setFinal(null); setChunks(0); setRisk(null); setVerdict(null);
    try {
      const s = await api.liveStart(vpId);
      setCheckId(s.check_id);
      await rec.start();
      timer.current = window.setInterval(async () => {
        if (!rec.recRef.current) return;
        const chunk = rec.recRef.current.takeWav();
        try {
          const r = await api.liveWindow(s.check_id, chunk);
          setRisk(r.running_risk); setVerdict(r.running_verdict); setChunks(r.windows_total);
        } catch { /* transient */ }
      }, 4000);
    } catch (e: any) { setErr(e.message); }
  };

  const end = async () => {
    if (timer.current) window.clearInterval(timer.current);
    const full = rec.recRef.current ? rec.recRef.current.snapshotWav() : null;
    await rec.stop();
    if (checkId) {
      try { setFinal(await api.liveFinish(checkId, vpId ? full : null)); }
      catch (e: any) { setErr(e.message); }
    }
    setCheckId(null);
  };

  return (
    <>
      <section className="card">
        <h2>{t("liveCheck", lang)}</h2>
        <p className="note">Put the call on speaker and keep this page open — or just speak near the phone for a demo.
          SwarRaksha listens in 4-second windows. It does not store the audio.</p>
        <label>Whose voice should this be? (optional)</label>
        <select value={vpId ?? ""} onChange={(e) => setVpId(e.target.value ? Number(e.target.value) : null)}>
          <option value="">No enrolled voice</option>
          {voiceprints.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
        </select>
        {!checkId
          ? <button className="primary" onClick={begin}>▶ Start live check</button>
          : <button className="danger" onClick={end}>⏹ Stop & get verdict</button>}
        {checkId && (
          <>
            <div className="meter big"><div className="meter-fill" style={{ width: `${Math.round((risk ?? 0) * 100)}%` }} /></div>
            <p className="note">{t("riskMeter", lang)}: {risk == null ? "…" : `${Math.round(risk * 100)}%`}
              {verdict && <> · {verdict.toUpperCase()}</>} · windows heard: {chunks}</p>
          </>
        )}
        {err && <p className="error">{err}</p>}
      </section>
      {final && <VerdictView result={final} lang={lang} />}
    </>
  );
}

/* ------------------------------------------------------------------ */
function EnrollScreen({ voiceprints, onChange }: { voiceprints: Voiceprint[]; onChange: () => void }) {
  const [label, setLabel] = useState("");
  const [samples, setSamples] = useState<(Blob | null)[]>([null, null, null]);
  const [slot, setSlot] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const rec = useRecorder();

  const recordSlot = async (i: number) => {
    if (slot === null) { setSlot(i); await rec.start(); }
    else { const b = await rec.stop(); const next = [...samples]; next[i] = b; setSamples(next); setSlot(null); }
  };

  return (
    <section className="card">
      <h2>Enroll a voice</h2>
      <p className="note">Record the person speaking naturally, 3 times, about 5–10 seconds each
        (for example, reading any sentence aloud). <strong>Only enroll a voice with that person's
        clear permission.</strong> We store a mathematical voiceprint — the recordings themselves are not kept.</p>
      <input placeholder="Whose voice? e.g. Son — Rohan" value={label} onChange={(e) => setLabel(e.target.value)} />
      {[0, 1, 2].map((i) => (
        <div key={i} className="row">
          <span>Sample {i + 1}: {samples[i] ? "✓ recorded" : "not recorded"}</span>
          <button onClick={() => recordSlot(i)}>{slot === i ? "⏹ Stop" : "🎙 Record"}</button>
        </div>
      ))}
      <button className="primary" disabled={busy || !label || samples.some((s) => !s)}
        onClick={async () => {
          setBusy(true); setMsg("");
          try { await api.createVoiceprint(label, samples as Blob[]); setMsg("Voice enrolled ✓"); setLabel(""); setSamples([null, null, null]); onChange(); }
          catch (e: any) { setMsg(e.message); }
          setBusy(false);
        }}>Enroll this voice</button>
      {msg && <p className="note">{msg}</p>}
      <h3>Enrolled voices</h3>
      {voiceprints.length === 0 && <p className="note">None yet.</p>}
      {voiceprints.map((v) => (
        <div key={v.id} className="row"><span>{v.label}</span>
          <button onClick={async () => { await api.deleteVoiceprint(v.id); onChange(); }}>Delete</button></div>
      ))}
    </section>
  );
}

/* ------------------------------------------------------------------ */
function FamilyScreen() {
  const [circles, setCircles] = useState<Circle[]>([]);
  const [name, setName] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [joinCode, setJoinCode] = useState("");
  const [msg, setMsg] = useState("");
  const load = useCallback(async () => { try { setCircles(await api.listCircles()); } catch { /* */ } }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <section className="card">
      <h2>Family circles</h2>
      <p className="note">A circle links the people who protect each other. If a check in your
        circle returns “likely cloned”, everyone in the circle gets an alert.</p>
      <div className="row">
        <input placeholder="New circle name, e.g. Family" value={name} onChange={(e) => setName(e.target.value)} />
        <button className="primary" onClick={async () => { await api.createCircle(name); setName(""); load(); }}>Create</button>
      </div>
      {circles.map((c) => (
        <div key={c.id} className="circle">
          <strong>{c.name}</strong>
          <ul>{c.members.map((m, i) => <li key={i}>{m.email || "—"} · {m.role} · {m.status}</li>)}</ul>
          <div className="row">
            <input placeholder="Invite by email" value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} />
            <button onClick={async () => {
              const r = await api.invite(c.id, inviteEmail);
              setInviteCode(r.invite_code); setMsg("Share this join code with them (they enter it below after signing in):");
            }}>Invite</button>
          </div>
        </div>
      ))}
      {inviteCode && <p className="note">{msg} <code>{inviteCode}</code></p>}
      <h3>Join a circle</h3>
      <div className="row">
        <input placeholder="Paste join code" value={joinCode} onChange={(e) => setJoinCode(e.target.value)} />
        <button className="primary" onClick={async () => { await api.joinCircle(joinCode); setJoinCode(""); load(); }}>Join</button>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
function HistoryScreen({ lang }: { lang: Lang }) {
  const [checks, setChecks] = useState<CheckResult[]>([]);
  const [open, setOpen] = useState<CheckResult | null>(null);
  useEffect(() => { api.listChecks().then(setChecks).catch(() => {}); }, []);
  return (
    <>
      <section className="card">
        <h2>{t("history", lang)}</h2>
        {checks.length === 0 && <p className="note">No checks yet.</p>}
        {checks.map((c) => (
          <div key={c.id} className="row">
            <span>{c.verdict ? VERDICT_EMOJI[c.verdict] : "…"} {c.type} · {c.created_at?.slice(0, 16).replace("T", " ")} · risk {Math.round((c.risk_score ?? 0) * 100)}%</span>
            <button onClick={() => setOpen(c)}>View</button>
          </div>
        ))}
      </section>
      {open && <VerdictView result={open} lang={lang} />}
    </>
  );
}

/* ------------------------------------------------------------------ */
function SettingsScreen({ lang, onLang, onLogout }: { lang: Lang; onLang: (l: Lang) => void; onLogout: () => void }) {
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [me, setMe] = useState<any>(null);
  useEffect(() => { api.alerts().then(setAlerts).catch(() => {}); api.me().then(setMe).catch(() => {}); }, []);
  return (
    <section className="card">
      <h2>{t("settings", lang)}</h2>
      {me && <p className="note">Signed in as {me.email}{me.name ? ` · ${me.name}` : ""}</p>}
      <label>Language / भाषा</label>
      <div className="row">
        <button className={lang === "en" ? "active" : ""} onClick={() => onLang("en")}>English</button>
        <button className={lang === "hi" ? "active" : ""} onClick={() => onLang("hi")}>हिन्दी</button>
      </div>
      <h3>Alerts</h3>
      {alerts.length === 0 && <p className="note">No alerts.</p>}
      {alerts.map((a) => (
        <div key={a.id} className="row"><span>{a.read ? "" : "🔔 "}{a.message}</span>
          {!a.read && <button onClick={async () => { await api.markAlertRead(a.id); setAlerts(await api.alerts()); }}>Mark read</button>}</div>
      ))}
      <button className="danger" onClick={onLogout}>Sign out</button>
    </section>
  );
}
