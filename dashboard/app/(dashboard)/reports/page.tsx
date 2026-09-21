'use client';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { apiClient, getErrorMessage } from '@/lib/api-client';
import type { DetectionFilters } from '@/lib/types';
import { FileText, Download, AlertCircle } from 'lucide-react';
import { format } from 'date-fns';
import styles from './reports.module.css';
const reportSchema = z.object({
  format: z.enum(['csv', 'pdf']),
  status: z.string().optional(),
  severity: z.string().optional(),
  start_date: z.string().optional(),
  end_date: z.string().optional(),
});
type ReportFormData = z.infer<typeof reportSchema>;
export default function ReportsPage() {
  const [isExporting, setIsExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ReportFormData>({
    resolver: zodResolver(reportSchema),
    defaultValues: {
      format: 'csv',
    },
  });
  const onSubmit = async (data: ReportFormData) => {
    setError(null);
    setSuccess(null);
    setIsExporting(true);
    try {
      const filters: DetectionFilters = {};
      if (data.status) filters.status = data.status as any;
      if (data.severity) filters.severity = data.severity as any;
      if (data.start_date) filters.start_date = data.start_date;
      if (data.end_date) filters.end_date = data.end_date;
      const blob = await apiClient.exportDetections(filters, data.format);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `detections-${format(new Date(), 'yyyy-MM-dd-HHmmss')}.${data.format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
      setSuccess(`Successfully exported detections as ${data.format.toUpperCase()}`);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsExporting(false);
    }
  };
  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1 className={styles.title}>Export Reports</h1>
      </div>
      <div className={styles.content}>
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <FileText size={24} />
            <h2 className={styles.cardTitle}>Export Detections</h2>
          </div>
          <p className={styles.cardDescription}>
            Export detection data with optional filters. Choose between CSV format for data analysis
            or PDF format for sharing reports.
          </p>
          <form onSubmit={handleSubmit(onSubmit)} className={styles.form}>
            {error && (
              <div className={styles.error}>
                <AlertCircle size={20} />
                <span>{error}</span>
              </div>
            )}
            {success && (
              <div className={styles.success}>
                <Download size={20} />
                <span>{success}</span>
              </div>
            )}
            {}
            <div className={styles.field}>
              <label className={styles.label}>Export Format</label>
              <div className={styles.radioGroup}>
                <label className={styles.radioOption}>
                  <input type="radio" value="csv" {...register('format')} />
                  <span>CSV (Comma-Separated Values)</span>
                  <span className={styles.radioDescription}>
                    Best for data analysis in Excel or other tools
                  </span>
                </label>
                <label className={styles.radioOption}>
                  <input type="radio" value="pdf" {...register('format')} />
                  <span>PDF (Portable Document Format)</span>
                  <span className={styles.radioDescription}>
                    Best for sharing reports and documentation
                  </span>
                </label>
              </div>
              {errors.format && (
                <span className={styles.fieldError}>{errors.format.message}</span>
              )}
            </div>
            {}
            <div className={styles.filters}>
              <h3 className={styles.filtersTitle}>Filters (Optional)</h3>
              <div className={styles.filterRow}>
                <div className={styles.field}>
                  <label htmlFor="status" className={styles.label}>
                    Status
                  </label>
                  <select
                    id="status"
                    {...register('status')}
                    className={styles.select}
                    disabled={isExporting}
                  >
                    <option value="">All Statuses</option>
                    <option value="new">New</option>
                    <option value="confirmed">Confirmed</option>
                    <option value="assigned">Assigned</option>
                    <option value="fixed">Fixed</option>
                    <option value="verified">Verified</option>
                  </select>
                </div>
                <div className={styles.field}>
                  <label htmlFor="severity" className={styles.label}>
                    Severity
                  </label>
                  <select
                    id="severity"
                    {...register('severity')}
                    className={styles.select}
                    disabled={isExporting}
                  >
                    <option value="">All Severities</option>
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                  </select>
                </div>
              </div>
              <div className={styles.filterRow}>
                <div className={styles.field}>
                  <label htmlFor="start_date" className={styles.label}>
                    Start Date
                  </label>
                  <input
                    id="start_date"
                    type="date"
                    {...register('start_date')}
                    className={styles.input}
                    disabled={isExporting}
                  />
                </div>
                <div className={styles.field}>
                  <label htmlFor="end_date" className={styles.label}>
                    End Date
                  </label>
                  <input
                    id="end_date"
                    type="date"
                    {...register('end_date')}
                    className={styles.input}
                    disabled={isExporting}
                  />
                </div>
              </div>
            </div>
            <button
              type="submit"
              className={styles.submitButton}
              disabled={isExporting}
            >
              {isExporting ? (
                <>Generating Export...</>
              ) : (
                <>
                  <Download size={20} />
                  <span>Export Report</span>
                </>
              )}
            </button>
          </form>
        </div>
        {}
        <div className={styles.infoCard}>
          <h3 className={styles.infoTitle}>Export Information</h3>
          <div className={styles.infoSection}>
            <h4>CSV Format</h4>
            <ul>
              <li>All detection fields included</li>
              <li>Suitable for Excel, Google Sheets, data analysis</li>
              <li>Includes coordinates, metadata, timestamps</li>
              <li>File size: Small (~10KB per 100 detections)</li>
            </ul>
          </div>
          <div className={styles.infoSection}>
            <h4>PDF Format</h4>
            <ul>
              <li>Summary statistics and map snapshot</li>
              <li>Table of detections with key fields</li>
              <li>Suitable for reports and sharing</li>
              <li>File size: Larger (~100KB per 100 detections)</li>
            </ul>
          </div>
          <div className={styles.infoSection}>
            <h4>Data Included</h4>
            <ul>
              <li>Detection ID and status</li>
              <li>Location (latitude/longitude)</li>
              <li>Severity and confidence</li>
              <li>Device information</li>
              <li>Detection timestamp</li>
              <li>Model version</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
