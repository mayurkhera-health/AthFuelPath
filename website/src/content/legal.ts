/**
 * Copied verbatim from fuelup-mobile/constants/legal.ts (July 2, 2026).
 * Keep in sync — the app also serves this via GET /api/legal/*.
 */
export const LEGAL_EFFECTIVE_DATE = "July 2, 2026";
export const LEGAL_LAST_UPDATED   = "July 2, 2026";

export type Section =
  | { type: "heading"; text: string }
  | { type: "body"; text: string }
  | { type: "bullets"; items: string[] }
  | { type: "warning"; text: string }
  | { type: "divider" }
  | { type: "table"; headers: string[]; rows: string[][] };

export const TERMS_OF_SERVICE: Section[] = [
  {
    type: "warning",
    text: "AthFuelPath provides educational food and nutrition guidance only. It is NOT medical nutrition therapy, medical advice, diagnosis, or treatment. Always consult a qualified professional for medical or individual nutrition concerns.",
  },
  { type: "heading", text: "1. Who We Are" },
  {
    type: "body",
    text: "AthFuelPath ('AthFuelPath,' 'we,' 'us') is an educational sports-nutrition application operated by Food Explorers LLC, San Jose, California. AthFuelPath helps youth athletes and their parents or guardians learn science-based eating habits timed around training and games.",
  },
  { type: "divider" },
  { type: "heading", text: "2. AthFuelPath Is Educational — Not Medical Advice" },
  {
    type: "body",
    text: "AthFuelPath provides general educational food and nutrition guidance. It is NOT medical nutrition therapy, medical advice, diagnosis, or treatment. AthFuelPath does not replace a physician, registered dietitian, or other qualified health professional. Always consult a qualified professional for any medical or individual nutrition concern, and before making significant changes to a child's diet, especially where allergies, medical conditions, or disordered-eating concerns exist.",
  },
  {
    type: "body",
    text: "Nutrition recommendations are based on published pediatric and sports-nutrition research and are presented as estimates and general guidance, not individualized medical prescriptions.",
  },
  { type: "divider" },
  { type: "heading", text: "3. Who May Use AthFuelPath" },
  {
    type: "bullets",
    items: [
      "AthFuelPath is intended for youth athletes ages 13–17 and their parents or guardians.",
      "An account must be created and controlled by a parent or legal guardian (18+).",
      "By creating an account, the parent/guardian confirms they are the parent or legal guardian of the athlete and that the athlete is within the supported age range.",
      "AthFuelPath does not knowingly permit children under 13 to create accounts or provide personal information without verifiable parental consent.",
    ],
  },
  { type: "divider" },
  { type: "heading", text: "4. What You Agree To" },
  {
    type: "bullets",
    items: [
      "Provide accurate information (age, weight, height, schedule, etc.) so guidance is appropriate.",
      "Use AthFuelPath only for its intended educational purpose.",
      "Not rely on AthFuelPath for medical decisions.",
      "Supervise your child's use of the app.",
    ],
  },
  { type: "divider" },
  { type: "heading", text: "5. Safety and Wellbeing" },
  {
    type: "body",
    text: "AthFuelPath is designed to encourage adequate, positive fueling and healthy habits. It is not designed for weight loss, calorie restriction, or any restrictive dietary purpose. If you have concerns about your child's relationship with food, eating patterns, growth, or health, consult a qualified professional. AthFuelPath may display educational safety information (for example, about supplements or hydration) but this does not constitute medical advice.",
  },
  { type: "divider" },
  { type: "heading", text: "6. Accounts and Acceptable Use" },
  {
    type: "body",
    text: "You are responsible for keeping account credentials secure. Do not misuse the service, attempt to access other users' data, or use AthFuelPath unlawfully. We may suspend accounts that violate these terms.",
  },
  { type: "divider" },
  { type: "heading", text: "7. Intellectual Property" },
  {
    type: "body",
    text: "All content, features, and functionality of AthFuelPath — including but not limited to text, graphics, AI-generated guidance, nutrition plans, and software — are owned by Food Explorers LLC and are protected by applicable intellectual property laws. You are granted a limited, non-exclusive, non-transferable license to use the app for its intended personal, non-commercial educational purpose. You may not reproduce, distribute, modify, or create derivative works from any part of AthFuelPath without our prior written consent.",
  },
  { type: "divider" },
  { type: "heading", text: "8. Third-Party Services" },
  {
    type: "body",
    text: "AthFuelPath uses third-party services to function (for example, nutrition databases, weather data, and AI services). Their handling of data is governed by their own terms. Nutrition data may be powered by third-party databases; attribution is provided where required.",
  },
  { type: "divider" },
  { type: "heading", text: "9. Disclaimers and Limitation of Liability" },
  {
    type: "body",
    text: "AthFuelPath is provided \"as is\" without warranties of any kind. To the maximum extent permitted by law, Food Explorers LLC is not liable for any indirect, incidental, or consequential damages arising from use of the service, including any health outcome.",
  },
  { type: "divider" },
  { type: "heading", text: "10. Governing Law" },
  {
    type: "body",
    text: "These Terms are governed by and construed in accordance with the laws of the State of California, without regard to its conflict of law provisions. Any disputes arising under these Terms shall be subject to the exclusive jurisdiction of the state and federal courts located in Santa Clara County, California.",
  },
  { type: "divider" },
  { type: "heading", text: "11. Severability" },
  {
    type: "body",
    text: "If any provision of these Terms is found to be unenforceable or invalid under applicable law, that provision will be limited or eliminated to the minimum extent necessary, and the remaining provisions will continue in full force and effect.",
  },
  { type: "divider" },
  { type: "heading", text: "12. Changes and Contact" },
  {
    type: "body",
    text: "We may update these Terms; material changes will be communicated in the app. If you have questions about these Terms, please contact us at support@athfuelpath.com.",
  },
];

export const PRIVACY_POLICY: Section[] = [
  {
    type: "body",
    text: "This policy explains what information AthFuelPath collects, why, how it is used and protected, and the choices you have. It is written to be readable.",
  },
  { type: "heading", text: "1. Children's Privacy and COPPA Compliance" },
  {
    type: "body",
    text: "AthFuelPath is directed to youth athletes ages 13–17 and is operated by parents or guardians on their behalf. We comply with the Children's Online Privacy Protection Act (COPPA). We do not knowingly collect personal information from children under 13 without verifiable parental consent. All accounts are created and controlled by a parent or legal guardian (18+), who provides consent on behalf of their child at the time of account creation. If we learn that we have inadvertently collected information from a child under 13 without proper consent, we will promptly delete it. To request deletion, contact us at support@athfuelpath.com.",
  },
  {
    type: "body",
    text: "We practice data minimization — we collect only what is necessary to provide educational nutrition guidance. We do not use children's information for behavioral advertising and we do not sell personal information.",
  },
  { type: "divider" },
  { type: "heading", text: "2. What We Collect" },
  {
    type: "table",
    headers: ["Data", "Why We Collect It", "Notes"],
    rows: [
      ["Parent name + email", "Account, consent record, weekly reports", "Parent/guardian is the account holder"],
      ["Athlete first name + age", "Personalize guidance; confirm age range", "First name only"],
      ["Gender, height, weight", "Calculate nutrient + hydration targets", "Sensitive — shown to parent, not public"],
      ["Dietary needs + allergies", "Personalize guidance safely", "Safety-relevant"],
      ["Training/game schedule", "Time fuel windows around events", "Imported from team calendar or entered manually"],
      ["City / location of events", "Weather for hydration guidance", "City-level only; NOT precise GPS"],
      ["Meal confirmation logs", "Track fueling progress", "User-initiated confirmations only; no background capture"],
      ["Push notification token", "Deliver fuel window reminders", "Device token only; opt-in"],
      ["Problem reports", "Improve the app", "Submitted voluntarily via Settings → Report a Problem"],
    ],
  },
  { type: "divider" },
  { type: "heading", text: "3. Push Notifications" },
  {
    type: "body",
    text: "With your permission, AthFuelPath sends push notifications to remind athletes and parents about upcoming fuel windows and game-day preparation. You can manage or disable notifications at any time in your device's Settings or within the AthFuelPath app under Settings → Notifications. We do not send marketing or advertising notifications.",
  },
  { type: "divider" },
  { type: "heading", text: "4. How We Use Information" },
  {
    type: "bullets",
    items: [
      "To generate personalized educational nutrition guidance and reminders.",
      "To produce progress views for the athlete and reports for the parent.",
      "To operate, maintain, and improve the service.",
      "To respond to support requests and problem reports.",
    ],
  },
  {
    type: "warning",
    text: "We do not use children's information for behavioral advertising or sell it to any third party.",
  },
  { type: "divider" },
  { type: "heading", text: "5. How We Share Information" },
  {
    type: "body",
    text: "We share information only with service providers that help AthFuelPath function (for example, nutrition database providers, weather providers, AI services, cloud infrastructure, and push notification delivery), under agreements that limit their use of the data to providing services to us. We may disclose information if required by law or to protect the safety of our users. We do not sell personal information.",
  },
  { type: "divider" },
  { type: "heading", text: "6. Data Retention and Deletion" },
  {
    type: "bullets",
    items: [
      "We keep information only as long as needed to provide the service.",
      "Meal confirmation logs are kept on a rolling 90-day basis.",
      "A parent may request review or deletion of their family's data at any time by emailing support@athfuelpath.com; we will act on deletion requests within 30 days.",
      "You may also request account deletion directly in the app under Settings → Delete Account.",
    ],
  },
  { type: "divider" },
  { type: "heading", text: "7. Security" },
  {
    type: "body",
    text: "We use reasonable administrative and technical safeguards to protect information and restrict access to athlete data. No system is perfectly secure; we cannot guarantee absolute security.",
  },
  { type: "divider" },
  { type: "heading", text: "8. Your Choices and Rights" },
  {
    type: "body",
    text: "Parents can review, update, or delete their family's information at any time. You can opt out of push notifications in app settings. California residents may have additional rights under the California Consumer Privacy Act (CCPA/CPRA), including the right to know what personal information is collected, the right to delete, and the right to opt out of sale (we do not sell data). To exercise any of these rights, contact us at support@athfuelpath.com.",
  },
  { type: "divider" },
  { type: "heading", text: "9. Changes to This Policy" },
  {
    type: "body",
    text: "We may update this Privacy Policy from time to time. Material changes will be communicated within the app. Continued use of AthFuelPath after changes are posted constitutes your acceptance of the revised policy.",
  },
  { type: "divider" },
  { type: "heading", text: "10. Contact" },
  {
    type: "body",
    text: "Food Explorers LLC · support@athfuelpath.com · San Jose, California.",
  },
];
