import { ABOUT_MESSAGES } from './messages';

export const metadata = {
  title: 'About',
  description: ABOUT_MESSAGES.intro.en,
};

export default function AboutLayout({ children }: { children: React.ReactNode }) {
  return children;
}
