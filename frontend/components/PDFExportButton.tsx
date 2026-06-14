'use client';

import { useAuth } from '@/lib/auth/AuthProvider';
import { motion } from 'framer-motion';
import { Download, Loader2, Lock } from 'lucide-react';
import { useCallback, useState } from 'react';

interface PDFExportButtonProps {
  /** Text for the button */
  label?: string;
  /** CSS selector identifying the printable region (defaults to <main>) */
  printSelector?: string;
  /** Document title for the PDF filename */
  documentTitle?: string;
  /** Show compact icon-only button */
  compact?: boolean;
  className?: string;
}

/**
 * Export-to-PDF button.
 *
 * Logged-in users can click to trigger a browser print dialog pre-configured
 * for PDF export. The `@media print` styles in globals.css handle the rest:
 *   - hides nav, footer, unnecessary chrome
 *   - applies clean typography on white background
 *
 * Unauthenticated users see a "Sign in to export" prompt which opens
 * the auth modal via the global custom event.
 */
export default function PDFExportButton({
  label = 'Export PDF',
  printSelector = 'main',
  documentTitle,
  compact = false,
  className = '',
}: PDFExportButtonProps) {
  const { isAuthenticated } = useAuth();
  const [exporting, setExporting] = useState(false);

  const handleExport = useCallback(() => {
    if (!isAuthenticated) {
      window.dispatchEvent(new CustomEvent('open-auth-modal'));
      return;
    }

    setExporting(true);

    // Briefly set a data attribute for print CSS scoping
    const origTitle = document.title;
    if (documentTitle) document.title = documentTitle;

    // Add print-ready class for optional targeted printing
    document.body.classList.add('pdf-export-active');

    // Give browser a tick to repaint
    requestAnimationFrame(() => {
      window.print();

      // Cleanup after dialog closes
      const cleanup = () => {
        document.body.classList.remove('pdf-export-active');
        document.title = origTitle;
        setExporting(false);
      };

      // Print dialog is synchronous in most browsers
      setTimeout(cleanup, 500);
    });
  }, [isAuthenticated, documentTitle]);

  if (compact) {
    return (
      <button
        onClick={handleExport}
        disabled={exporting}
        title={isAuthenticated ? label : 'Sign in to export PDF'}
        className={`p-2 rounded-lg transition-all ${
          isAuthenticated
            ? 'text-gov-forest/60 dark:text-emerald-100/60 hover:text-gov-sage hover:bg-gov-sage/10'
            : 'text-gov-forest/30 dark:text-emerald-100/30 hover:text-gov-forest/50 dark:text-emerald-100/50'
        } disabled:opacity-50 ${className}`}>
        {exporting ? (
          <Loader2 className='w-4 h-4 animate-spin' />
        ) : isAuthenticated ? (
          <Download className='w-4 h-4' />
        ) : (
          <Lock className='w-4 h-4' />
        )}
      </button>
    );
  }

  return (
    <motion.button
      onClick={handleExport}
      disabled={exporting}
      whileTap={{ scale: 0.96 }}
      className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition-all border shadow-sm ${
        isAuthenticated
          ? 'bg-white/80 dark:bg-surface-elevated text-gov-forest/70 dark:text-emerald-100/70 border-gov-sage/20 hover:bg-gov-sage/10 hover:text-gov-sage'
          : 'bg-white/60 dark:bg-surface-elevated text-gov-forest/40 dark:text-emerald-100/40 border-gov-sage/10 hover:bg-white/80 dark:bg-surface-elevated'
      } disabled:opacity-50 ${className}`}>
      {exporting ? (
        <Loader2 className='w-4 h-4 animate-spin' />
      ) : isAuthenticated ? (
        <Download className='w-4 h-4' />
      ) : (
        <Lock className='w-4 h-4' />
      )}
      {label}
    </motion.button>
  );
}
