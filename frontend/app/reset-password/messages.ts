import type { Translation } from '@/lib/i18n/messages';

export const resetMessages = {
  title: { en: "Choose a new password", sw: "Chagua nenosiri jipya", plain: "Choose a new password" },
  rules: {
    en: "Use at least 8 characters, including an uppercase letter (A–Z), a lowercase letter (a–z) and a number (0–9).",
    sw: "Tumia angalau vibambo 8, vikiwemo herufi kubwa (A–Z), herufi ndogo (a–z) na tarakimu (0–9).",
    plain: "Use 8 or more characters. Include a capital letter (A–Z), a small letter (a–z) and a number (0–9).",
  },
  window: {
    en: "You have up to five minutes to save after opening a valid reset link.",
    sw: "Una hadi dakika tano kuhifadhi baada ya kufungua kiungo halali cha kubadili nenosiri.",
    plain: "You have up to five minutes to save after you open a valid reset link.",
  },
  password: { en: "New password", sw: "Nenosiri jipya", plain: "New password" },
  confirmation: { en: "Type it again", sw: "Liandike tena", plain: "Type it again" },
  showPassword: { en: "Show new password", sw: "Onyesha nenosiri jipya", plain: "Show new password" },
  hidePassword: { en: "Hide new password", sw: "Ficha nenosiri jipya", plain: "Hide new password" },
  showConfirmation: { en: "Show confirmation password", sw: "Onyesha nenosiri la kuthibitisha", plain: "Show the password you typed again" },
  hideConfirmation: { en: "Hide confirmation password", sw: "Ficha nenosiri la kuthibitisha", plain: "Hide the password you typed again" },
  save: { en: "Save password", sw: "Hifadhi nenosiri", plain: "Save password" },
  saving: { en: "Saving password…", sw: "Inahifadhi nenosiri…", plain: "Saving password…" },
  loading: { en: "Loading the reset form…", sw: "Inapakia fomu ya kubadili nenosiri…", plain: "Loading the reset form…" },
  updated: { en: "Password updated", sw: "Nenosiri limebadilishwa", plain: "Password updated" },
  redirecting: { en: "Taking you to the homepage…", sw: "Inakupeleka kwenye ukurasa wa mwanzo…", plain: "Taking you to the homepage…" },
  invalid: { en: "Reset password", sw: "Badili nenosiri", plain: "Reset password" },
  reopen: {
    en: "Open your latest reset link or request a new one from Sign in.",
    sw: "Fungua kiungo chako cha karibuni cha kubadili nenosiri au omba kipya kupitia Ingia.",
    plain: "Open the newest reset link or go to Sign in to ask for another.",
  },
  home: { en: "Back to homepage", sw: "Rudi kwenye ukurasa wa mwanzo", plain: "Back to homepage" },
  requirements: { en: "Password does not meet the requirements.", sw: "Nenosiri halikidhi masharti.", plain: "Check that your password follows all the rules above." },
  mismatch: { en: "Passwords do not match.", sw: "Manenosiri hayalingani.", plain: "The passwords are different." },
  failed: {
    en: "Could not update your password. If the link has expired, request a new one.",
    sw: "Nenosiri halikuweza kubadilishwa. Ikiwa kiungo kimeisha muda wake, omba kipya.",
    plain: "We could not save your password. If your link has expired, ask for a new one.",
  },
} as const satisfies Record<string, Translation>;
