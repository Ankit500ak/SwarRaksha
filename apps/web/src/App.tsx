import { useCallback, useEffect, useRef, useState } from "react";
import { api, hasToken, setToken, type CheckResult, type Circle, type Voiceprint, type AlertItem } from "./api";
import { t, type Lang } from "./i18n";
import { WavRecorder } from "./recorder";

type Tab = "home" | "live" | "enroll" | "family" | "history" | "settings" | "privacy" | "terms";

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

  if (!authed) {
    if (tab === "privacy" || tab === "terms")
      return <LegalScreen kind={tab} lang={lang} onBack={() => setTab("home")} />;
    return <Landing onLogin={() => setAuthed(true)} lang={lang} onLegal={(k) => setTab(k)} />;
  }

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
        {(tab === "privacy" || tab === "terms") && <LegalScreen kind={tab} lang={lang} onBack={() => setTab("settings")} />}
      </main>
      <footer>
        Baseline demo build — the detector is an untrained heuristic (see MODEL_CARD). Risk, never certainty.
        <div className="row" style={{ justifyContent: "center" }}>
          <button onClick={() => setTab("privacy")}>{t("privacy", lang)}</button>
          <button onClick={() => setTab("terms")}>{t("terms", lang)}</button>
        </div>
      </footer>
    </div>
  );
}

/* ------------------------------------------------------------------ */
function Landing({ onLogin, lang, onLegal }: { onLogin: () => void; lang: Lang; onLegal: (k: "privacy" | "terms") => void }) {
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
        <p className="note" style={{ textAlign: "center" }}>
          <button onClick={() => onLegal("privacy")}>{t("privacy", lang)}</button>{" "}
          <button onClick={() => onLegal("terms")}>{t("terms", lang)}</button>
        </p>
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
/* Privacy Policy & Terms — plain language, DPDP-aligned (PLAN §11).
 * Body copy lives here as lang-keyed sections; headings/buttons use
 * i18n.ts. The contact is a placeholder until the operator publishes
 * real grievance-contact details (see docs/deployment.md). */
const LEGAL: Record<"privacy" | "terms", Record<Lang, { title: string; sections: { h: string; p: string }[] }>> = {
  privacy: {
    en: {
      title: "Privacy Policy",
      sections: [
        { h: "What we store", p: "Your email address, name and language choice; voiceprints — mathematical summaries (embeddings) of enrolled voices, not the recordings themselves; your check results (verdicts and scores, not the audio); family-circle membership; alerts and any scam reports you send; and the time you agreed to enroll a voice (consent record)." },
        { h: "What we do NOT store", p: "By default we do not keep raw audio. Recordings you check and enrollment samples are processed to produce scores and embeddings and are then discarded, unless you separately and explicitly agree to donate a sample for research." },
        { h: "Why we use it", p: "Only to run the service: checking voices, matching them against voices you enrolled, warning your family circle, and keeping your account secure. We do not sell your data, and we do not use voiceprints to identify people outside your own enrolled family voices." },
        { h: "Consent", p: "Enroll only your own voice, or a family member's voice with that person's clear permission. You can withdraw consent at any time by deleting a voiceprint (in Enroll) or deleting your account (in Settings) — deletion removes the stored embeddings." },
        { h: "Your rights (DPDP Act)", p: "You have the right to see and download your data, correct it, and have it erased. Use “Download my data” and “Delete my account” in Settings, or contact us. Deleting your account permanently removes your account, voiceprints, checks and alerts." },
        { h: "Security & honesty", p: "Voiceprints are sensitive. Our plan (PLAN.md §11) requires embeddings to be encrypted at rest; in this baseline demo build they are not yet encrypted and the detector is an untrained heuristic — please treat this build as a demo, not a finished safety product. If we ever discover a data breach affecting you, we will inform you and the authorities as the DPDP Act requires." },
        { h: "Contact", p: "Privacy questions or grievances: [operator to publish a privacy contact email and grievance officer details here before public launch]." },
      ],
    },
    hi: {
      title: "गोपनीयता नीति",
      sections: [
        { h: "हम क्या रखते हैं", p: "आपका ईमेल पता, नाम और भाषा की पसंद; वॉइसप्रिंट — दर्ज आवाज़ों का गणितीय सार (एम्बेडिंग), रिकॉर्डिंग खुद नहीं; आपकी जाँच के नतीजे (फैसला और स्कोर, आवाज़ नहीं); परिवार-सर्कल की सदस्यता; अलर्ट और आपकी भेजी रिपोर्ट; और आवाज़ दर्ज करने की सहमति का समय।" },
        { h: "हम क्या नहीं रखते", p: "आम तौर पर हम असली आवाज़ (कच्चा ऑडियो) नहीं रखते। आप जो रिकॉर्डिंग जाँचते हैं और दर्ज करने के नमूने, वे स्कोर और एम्बेडिंग बनाने के बाद हटा दिए जाते हैं — जब तक आप अलग से, साफ़ तौर पर, शोध के लिए नमूना देने की सहमति न दें।" },
        { h: "हम इसका उपयोग क्यों करते हैं", p: "सिर्फ सेवा चलाने के लिए: आवाज़ जाँचना, दर्ज आवाज़ों से मिलान करना, आपके परिवार को चेतावनी देना और आपका खाता सुरक्षित रखना। हम आपका डेटा नहीं बेचते, और वॉइसप्रिंट का उपयोग आपके अपने परिवार की दर्ज आवाज़ों के बाहर किसी को पहचानने के लिए नहीं करते।" },
        { h: "सहमति", p: "सिर्फ अपनी आवाज़ दर्ज करें, या परिवार के सदस्य की आवाज़ उनकी साफ़ अनुमति से। आप कभी भी वॉइसप्रिंट हटाकर (दर्ज करें पेज से) या खाता हटाकर (सेटिंग्स से) सहमति वापस ले सकते हैं — हटाने से रखी हुई एम्बेडिंग भी हट जाती हैं।" },
        { h: "आपके अधिकार (DPDP कानून)", p: "आपको अपना डेटा देखने और डाउनलोड करने, उसे सुधारने और हटवाने का अधिकार है। सेटिंग्स में “मेरा डेटा डाउनलोड करें” और “मेरा खाता हटाएँ” का उपयोग करें, या हमसे संपर्क करें। खाता हटाने से आपका खाता, वॉइसप्रिंट, जाँचें और अलर्ट हमेशा के लिए हट जाते हैं।" },
        { h: "सुरक्षा और सच्चाई", p: "वॉइसप्रिंट संवेदनशील होते हैं। हमारी योजना (PLAN.md §11) के अनुसार एम्बेडिंग सुरक्षित (एन्क्रिप्ट) रखी जानी चाहिए; इस शुरुआती डेमो बिल्ड में वे अभी एन्क्रिप्ट नहीं हैं और पहचानने वाला मॉडल अभी प्रशिक्षित नहीं है — कृपया इस बिल्ड को डेमो समझें, तैयार सुरक्षा उत्पाद नहीं। यदि कभी आपके डेटा की चोरी/लीक का पता चले तो हम DPDP कानून के अनुसार आपको और अधिकारियों को सूचित करेंगे।" },
        { h: "संपर्क", p: "गोपनीयता से जुड़े सवाल या शिकायत: [संचालक सार्वजनिक लॉन्च से पहले यहाँ गोपनीयता संपर्क ईमेल और शिकायत अधिकारी का विवरण डालेंगे]।" },
      ],
    },
  },
  terms: {
    en: {
      title: "Terms of Use",
      sections: [
        { h: "What SwarRaksha is — and is not", p: "SwarRaksha gives a risk indication about a voice: verified, be careful, or likely cloned. It is never a guarantee. A green result does not prove a caller is genuine, and a red result does not prove fraud. For money matters, always call the person back on their saved number." },
        { h: "Not an emergency service", p: "If you believe a crime is happening, contact your bank and the police / national cyber-fraud helpline in your country. Do not rely on this app in an emergency." },
        { h: "Your responsibilities", p: "Enroll only voices you have permission to enroll. Do not use SwarRaksha to test or improve voice clones, to check people without a legitimate reason, or to harass anyone. Keep your sign-in code private." },
        { h: "Accounts & availability", p: "This is an early demo build: the detector is an untrained heuristic, results can be wrong, and the service may change or be unavailable. We may suspend accounts that abuse the service (for example, repeatedly testing cloned voices)." },
        { h: "Liability", p: "Decisions you take — including sending or refusing money — are yours. To the extent the law allows, we are not liable for losses arising from reliance on a verdict. Nothing in these terms limits rights you have under Indian law, including the DPDP Act." },
        { h: "Contact", p: "Questions about these terms: [operator to publish a contact email here before public launch]." },
      ],
    },
    hi: {
      title: "उपयोग की शर्तें",
      sections: [
        { h: "SwarRaksha क्या है — और क्या नहीं", p: "SwarRaksha आवाज़ के बारे में खतरे का संकेत देता है: सही पाई गई, सावधान रहें, या लगता है नकली है। यह कभी गारंटी नहीं है। हरा नतीजा यह साबित नहीं करता कि कॉलर असली है, और लाल नतीजा धोखाधड़ी साबित नहीं करता। पैसे के मामले में हमेशा व्यक्ति को उनके सेव किए नंबर पर खुद कॉल करें।" },
        { h: "यह आपातकालीन सेवा नहीं है", p: "यदि आपको लगता है कि अपराध हो रहा है, तो अपने बैंक और पुलिस / अपने देश की राष्ट्रीय साइबर-धोखाधड़ी हेल्पलाइन से संपर्क करें। आपात स्थिति में इस ऐप पर भरोसा न करें।" },
        { h: "आपकी ज़िम्मेदारियाँ", p: "सिर्फ वही आवाज़ें दर्ज करें जिनकी अनुमति आपके पास है। SwarRaksha का उपयोग आवाज़-क्लोन जाँचने या सुधारने के लिए, बिना उचित कारण किसी की जाँच के लिए, या किसी को परेशान करने के लिए न करें। अपना साइन-इन कोड गुप्त रखें।" },
        { h: "खाते और उपलब्धता", p: "यह एक शुरुआती डेमो बिल्ड है: पहचानने वाला मॉडल अभी प्रशिक्षित नहीं है, नतीजे गलत हो सकते हैं, और सेवा बदल या बंद हो सकती है। दुरुपयोग करने वाले खाते (जैसे बार-बार क्लोन आवाज़ें जाँचना) हम रोक सकते हैं।" },
        { h: "ज़िम्मेदारी की सीमा", p: "आप जो फैसले लेते हैं — पैसे भेजना या न भेजना समेत — वे आपके हैं। कानून जितनी अनुमति देता है, किसी फैसले पर भरोसा करने से हुए नुकसान के लिए हम ज़िम्मेदार नहीं हैं। इन शर्तों से भारतीय कानून, DPDP कानून समेत, के तहत आपके अधिकार कम नहीं होते।" },
        { h: "संपर्क", p: "इन शर्तों पर सवाल: [संचालक सार्वजनिक लॉन्च से पहले यहाँ संपर्क ईमेल डालेंगे]।" },
      ],
    },
  },
};

function LegalScreen({ kind, lang, onBack }: { kind: "privacy" | "terms"; lang: Lang; onBack: () => void }) {
  const doc = LEGAL[kind][lang];
  return (
    <div className="shell">
      <main>
        <section className="card">
          <h2>{doc.title}</h2>
          {doc.sections.map((s) => (
            <div key={s.h}><h3>{s.h}</h3><p>{s.p}</p></div>
          ))}
          <button onClick={onBack}>{t("back", lang)}</button>
        </section>
      </main>
    </div>
  );
}

/* ------------------------------------------------------------------ */
function SettingsScreen({ lang, onLang, onLogout }: { lang: Lang; onLang: (l: Lang) => void; onLogout: () => void }) {
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [me, setMe] = useState<any>(null);
  const [dataMsg, setDataMsg] = useState("");
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  useEffect(() => { api.alerts().then(setAlerts).catch(() => {}); api.me().then(setMe).catch(() => {}); }, []);

  const downloadData = async () => {
    setDataMsg("");
    try {
      const data = await api.exportMe();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = "swarraksha-my-data.json"; a.click();
      URL.revokeObjectURL(url);
      setDataMsg(t("downloadStarted", lang));
    } catch (e: any) { setDataMsg(e.message); }
  };

  const deleteAccount = async () => {
    if (!confirmingDelete) { setConfirmingDelete(true); return; }
    try { await api.deleteMe(); onLogout(); }
    catch (e: any) { setDataMsg(e.message); setConfirmingDelete(false); }
  };
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
      <h3>{t("yourData", lang)}</h3>
      <div className="row">
        <button onClick={downloadData}>{t("downloadData", lang)}</button>
        <button className="danger" onClick={deleteAccount}>
          {confirmingDelete ? (lang === "hi" ? "हटाना सुनिश्चित करें" : "Confirm delete") : t("deleteAccount", lang)}
        </button>
        {confirmingDelete && <button onClick={() => setConfirmingDelete(false)}>{t("back", lang)}</button>}
      </div>
      {confirmingDelete && <p className="error">{t("deleteAccountConfirm", lang)}</p>}
      {dataMsg && <p className="note">{dataMsg}</p>}
      <button className="danger" onClick={onLogout}>Sign out</button>
    </section>
  );
}
