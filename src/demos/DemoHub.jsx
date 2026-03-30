import React from 'react';
import { Link } from 'react-router-dom';

const demos = [
  {
    title: "Hard Money Lending Portal",
    description: "Loan management dashboard, deal pipeline, borrower applications, and payment tracking for private lenders.",
    icon: "🏦",
    link: "/demos/lending",
    color: "#1a5c2a",
    tag: "Finance"
  },
  {
    title: "Real Estate Agent CRM",
    description: "Property listings, lead management, client tracking, and AI-powered market insights for realtors.",
    icon: "🏠",
    link: "/demos/realtor",
    color: "#2563eb",
    tag: "Real Estate"
  },
  {
    title: "Restaurant Management",
    description: "Menu management, online ordering, reservation system, and daily revenue tracking for restaurants.",
    icon: "🍽️",
    link: "/demos/restaurant",
    color: "#dc2626",
    tag: "Food & Beverage"
  }
];

export default function DemoHub() {
  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '40px 20px' }}>
      {/* Hero */}
      <div style={{
        textAlign: 'center',
        marginBottom: 50,
        padding: '60px 20px',
        background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 100%)',
        borderRadius: 20,
        color: '#fff'
      }}>
        <h1 style={{ fontSize: 42, fontWeight: 800, margin: 0 }}>Business Solutions Demo</h1>
        <p style={{ fontSize: 18, color: '#94a3b8', marginTop: 12, maxWidth: 600, margin: '12px auto 0' }}>
          Custom-built systems with AI integration to save your business time and money. See what we can build for you.
        </p>
        <div style={{
          display: 'inline-block',
          marginTop: 24,
          padding: '10px 24px',
          background: 'rgba(255,255,255,0.1)',
          borderRadius: 30,
          fontSize: 14,
          color: '#60a5fa'
        }}>
          Powered by AI &bull; Custom Built &bull; Fully Managed
        </div>
      </div>

      {/* Demo Cards */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(320, 1fr))',
        gap: 28
      }}>
        {demos.map((demo, i) => (
          <Link to={demo.link} key={i} style={{ textDecoration: 'none', color: 'inherit' }}>
            <div style={{
              background: '#fff',
              borderRadius: 16,
              padding: 32,
              boxShadow: '0 4px 24px rgba(0,0,0,0.08)',
              border: '1px solid #e2e8f0',
              transition: 'transform 0.2s, box-shadow 0.2s',
              cursor: 'pointer',
              minHeight: 220
            }}
            onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-4px)'; e.currentTarget.style.boxShadow = '0 12px 40px rgba(0,0,0,0.12)'; }}
            onMouseLeave={e => { e.currentTarget.style.transform = 'translateY(0)'; e.currentTarget.style.boxShadow = '0 4px 24px rgba(0,0,0,0.08)'; }}
            >
              <div style={{
                display: 'inline-block',
                padding: '6px 14px',
                background: demo.color + '15',
                color: demo.color,
                borderRadius: 20,
                fontSize: 12,
                fontWeight: 700,
                marginBottom: 16,
                letterSpacing: 0.5
              }}>{demo.tag}</div>
              <div style={{ fontSize: 48, marginBottom: 16 }}>{demo.icon}</div>
              <h3 style={{ fontSize: 22, fontWeight: 700, margin: '0 0 10px', color: '#0f172a' }}>{demo.title}</h3>
              <p style={{ fontSize: 15, color: '#64748b', lineHeight: 1.6, margin: 0 }}>{demo.description}</p>
              <div style={{ marginTop: 20, color: demo.color, fontWeight: 600, fontSize: 14 }}>
                View Demo →
              </div>
            </div>
          </Link>
        ))}
      </div>

      {/* Bottom CTA */}
      <div style={{
        textAlign: 'center',
        marginTop: 60,
        padding: '40px 20px',
        background: '#f8fafc',
        borderRadius: 16,
        border: '1px solid #e2e8f0'
      }}>
        <h3 style={{ fontSize: 22, fontWeight: 700, color: '#0f172a', margin: 0 }}>Don't see your industry?</h3>
        <p style={{ color: '#64748b', marginTop: 8, fontSize: 15 }}>
          We build custom solutions for any business. Let's talk about what you need.
        </p>
      </div>
    </div>
  );
}
