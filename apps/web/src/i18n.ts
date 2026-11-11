export type Lang = "en" | "hi";

/** Key UI strings. The verdict screen is fully bilingual; the rest of
 * the app translates its main labels. */
export const STR: Record<string, Record<Lang, string>> = {
  tagline: { en: "Every voice, verified.", hi: "हर आवाज़, जाँची हुई।" },
  checkRecording: { en: "Check a recording", hi: "रिकॉर्डिंग जाँचें" },
  liveCheck: { en: "Live check", hi: "लाइव जाँच" },
  enroll: { en: "Enroll a voice", hi: "आवाज़ दर्ज करें" },
  family: { en: "Family", hi: "परिवार" },
  history: { en: "History", hi: "पुरानी जाँचें" },
  settings: { en: "Settings", hi: "सेटिंग्स" },
  verified: { en: "Voice verified", hi: "आवाज़ सही पाई गई" },
  unverified: { en: "Unverified — be careful", hi: "पुष्टि नहीं हुई — सावधान रहें" },
  cloned: { en: "Likely a fake (cloned) voice", hi: "लगता है यह नकली (क्लोन) आवाज़ है" },
  whyTitle: { en: "Why we think so", hi: "हम ऐसा क्यों सोचते हैं" },
  whatNext: { en: "What to do now", hi: "अब क्या करें" },
  greenAdvice: {
    en: "The voice sounds human and matches the enrolled voice. Still, for money matters, follow your usual care.",
    hi: "आवाज़ असली लगती है और दर्ज आवाज़ से मिलती है। फिर भी पैसे के मामले में अपनी सामान्य सावधानी बरतें।",
  },
  yellowAdvice: {
    en: "Do not send money on this call. Hang up and call the person back on their saved number.",
    hi: "इस कॉल पर पैसे न भेजें। फोन काटकर व्यक्ति को उनके सेव किए हुए नंबर पर खुद कॉल करें।",
  },
  redAdvice: {
    en: "Do NOT send money. End the call now and call the person on their saved number. You can report this attempt below.",
    hi: "पैसे बिल्कुल न भेजें। कॉल अभी खत्म करें और व्यक्ति को उनके सेव किए हुए नंबर पर कॉल करें। नीचे इस कोशिश की रिपोर्ट कर सकते हैं।",
  },
  analysing: { en: "Listening carefully…", hi: "ध्यान से सुन रहे हैं…" },
  report: { en: "Report this attempt", hi: "इस कोशिश की रिपोर्ट करें" },
  riskMeter: { en: "Risk", hi: "खतरा" },
};

export function t(key: string, lang: Lang): string {
  return STR[key]?.[lang] ?? STR[key]?.en ?? key;
}
