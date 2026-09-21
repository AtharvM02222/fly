/**
 * Map view - main dashboard page (placeholder for full implementation).
 */

'use client';

export default function MapPage() {
  return (
    <div style={{ padding: '2rem' }}>
      <h1 style={{ fontSize: '2rem', fontWeight: 700, marginBottom: '1rem' }}>
        Detection Map
      </h1>
      <div style={{ 
        background: 'white', 
        padding: '3rem', 
        borderRadius: '8px', 
        textAlign: 'center',
        boxShadow: '0 1px 3px rgba(0,0,0,0.1)'
      }}>
        <p style={{ fontSize: '1.125rem', color: '#718096', marginBottom: '1rem' }}>
          Map view with Leaflet clustering
        </p>
        <p style={{ fontSize: '0.875rem', color: '#a0aec0' }}>
          See implementation guide for complete map component with detection markers
        </p>
      </div>
    </div>
  );
}
