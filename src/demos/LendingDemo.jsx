import React, { useState } from 'react';
import { Link } from 'react-router-dom';

// Fake loan data
const sampleLoans = [
  { id: 'LN-2024-001', borrower: 'Marcus Johnson', property: '1247 Oak Ave, Houston TX', amount: 285000, ltv: 68, rate: 12, term: 12, status: 'Active', funded: '2024-01-15', payments: 11 },
  { id: 'LN-2024-002', borrower: 'Sarah Williams', property: '892 Pine St, Dallas TX', amount: 420000, ltv: 72, rate: 11.5, term: 9, status: 'Active', funded: '2024-03-01', payments: 8 },
  { id: 'LN-2024-003', borrower: 'David Chen', property: '3301 Elm Blvd, Austin TX', amount: 195000, ltv: 65, rate: 13, term: 6, status: 'Paid Off', funded: '2024-02-10', payments: 6 },
  { id: 'LN-2024-004', borrower: 'Jennifer Martinez', property: '567 Maple Dr, San Antonio TX', amount: 350000, ltv: 70, rate: 12.5, term: 12, status: 'Active', funded: '2024-04-20', payments: 5 },
  { id: 'LN-2024-005', borrower: 'Robert Thompson', property: '2100 Cedar Ln, Fort Worth TX', amount: 510000, ltv: 75, rate: 11, term: 18, status: 'Late', funded: '2024-01-05', payments: 9 },
  { id: 'LN-2024-006', borrower: 'Amanda Foster', property: '445 Birch Way, Plano TX', amount: 178000, ltv: 60, rate: 12, term: 6, status: 'Review', funded: null, payments: 0 },
];

const stats = [
  { label: 'Total Portfolio', value: '$1,938,000', icon: '💰', change: '+12%', color: '#059669' },
  { label: 'Active Loans', value: '4', icon: '📋', change: '+2 this month', color: '#2563eb' },
  { label: 'Avg LTV', value: '68.3%', icon: '📊', change: 'Within target', color: '#7c3aed' },
  { label: 'Monthly Revenue', value: '$19,240', icon: '📈', change: '+8% vs last mo', color: '#ea580c' },
];

const statusColors = {
  Active: { bg: '#dcfce7', text: '#166534' },
  'Paid Off': { bg: '#dbeafe', text: '#1e40af' },
  Late: { bg: '#fee2e2', text: '#991b1b' },
  Review: { bg: '#fef3c7', text: '#92400e' },
};

const aiInsights = [
  { type: 'warning', text: 'LN-2024-005 (Robert Thompson) is 15 days past due on payment #10. Recommend sending notice.' },
  { type: 'opportunity', text: 'New application from Amanda Foster — property ARV estimated at $296,000. LTV at 60% is well within guidelines.' },
  { type: 'info', text: 'Portfolio weighted average rate: 12.0%. Market average for similar lenders: 11.8%. Competitive positioning is strong.' },
  { type: 'success', text: 'David Chen loan fully paid off ahead of schedule. Total interest earned: $12,675. Consider for future deals.' },
];

const insightIcons = { warning: '⚠️', opportunity: '🎯', info: '📊', success: '✅' };
const insightColors = { warning: '#fef3c7', opportunity: '#ede9fe', info: '#dbeafe', success: '#dcfce7' };

export default function LendingDemo() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [showAI, setShowAI] = useState(false);
  const [aiChat, setAiChat] = useState('');
  const [chatMessages, setChatMessages] = useState([
    { role: 'ai', text: "Hi! I'm your AI lending assistant. Ask me about your portfolio, borrower risk, or market conditions." }
  ]);

  const handleChat = (e) => {
    e.preventDefault();
    if (!aiChat.trim()) return;
    const userMsg = aiChat;
    setChatMessages(prev => [...prev, { role: 'user', text: userMsg }]);
    setAiChat('');
    setTimeout(() => {
      let response = "Based on your current portfolio of $1.94M across 4 active loans, your risk exposure is moderate. The late payment on LN-2024-005 should be addressed — I'd recommend a formal notice followed by a 5-day cure period before escalating.";
      if (userMsg.toLowerCase().includes('arv') || userMsg.toLowerCase().includes('property')) {
        response = "Running comps analysis... The property at 445 Birch Way shows recent sales in the area averaging $285-310K. At a purchase price of $178K, the borrower has solid equity margin. ARV estimate: $296,000. Recommended max loan: $207,200 (70% LTV).";
      } else if (userMsg.toLowerCase().includes('rate') || userMsg.toLowerCase().includes('market')) {
        response = "Current hard money market rates in Texas range from 10-14% for fix-and-flip loans. Your weighted average of 12% is competitive. I'd suggest 11.5% for repeat borrowers to improve retention, and 13% for first-time borrowers to offset risk.";
      } else if (userMsg.toLowerCase().includes('risk') || userMsg.toLowerCase().includes('late')) {
        response = "Portfolio risk assessment: 1 of 4 active loans (25%) is currently late. Robert Thompson's payment history shows on-time for 9 months before this miss — likely a one-time issue. Recommend reaching out before formal default proceedings.";
      }
      setChatMessages(prev => [...prev, { role: 'ai', text: response }]);
    }, 1200);
  };

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: '20px' }}>
      {/* Top Bar */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: 28, flexWrap: 'wrap', gap: 12
      }}>
        <div>
          <Link to="/demos" style={{ color: '#64748b', textDecoration: 'none', fontSize: 13 }}>← Back to Demos</Link>
          <h1 style={{ fontSize: 28, fontWeight: 800, color: '#0f172a', margin: '8px 0 0' }}>
            🏦 Capital Bridge Lending
          </h1>
          <p style={{ color: '#64748b', margin: '4px 0 0', fontSize: 14 }}>Hard Money Loan Management System</p>
        </div>
        <button
          onClick={() => setShowAI(!showAI)}
          style={{
            padding: '12px 24px', background: 'linear-gradient(135deg, #7c3aed, #2563eb)',
            color: '#fff', border: 'none', borderRadius: 12, cursor: 'pointer',
            fontWeight: 700, fontSize: 14, boxShadow: '0 4px 14px rgba(37,99,235,0.3)'
          }}
        >
          {showAI ? '✕ Close AI Assistant' : '🤖 AI Assistant'}
        </button>
      </div>

      {/* AI Chat Panel */}
      {showAI && (
        <div style={{
          background: '#fff', borderRadius: 16, padding: 24, marginBottom: 24,
          border: '2px solid #7c3aed', boxShadow: '0 8px 30px rgba(124,58,237,0.15)'
        }}>
          <h3 style={{ margin: '0 0 16px', color: '#7c3aed', fontSize: 16 }}>🤖 AI Lending Assistant</h3>
          <div style={{
            maxHeight: 250, overflowY: 'auto', marginBottom: 16, padding: 12,
            background: '#f8fafc', borderRadius: 12
          }}>
            {chatMessages.map((msg, i) => (
              <div key={i} style={{
                marginBottom: 12, display: 'flex',
                justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start'
              }}>
                <div style={{
                  maxWidth: '80%', padding: '10px 16px', borderRadius: 12,
                  background: msg.role === 'user' ? '#2563eb' : '#fff',
                  color: msg.role === 'user' ? '#fff' : '#0f172a',
                  fontSize: 14, lineHeight: 1.6,
                  boxShadow: '0 2px 8px rgba(0,0,0,0.06)'
                }}>
                  {msg.text}
                </div>
              </div>
            ))}
          </div>
          <form onSubmit={handleChat} style={{ display: 'flex', gap: 10 }}>
            <input
              value={aiChat}
              onChange={e => setAiChat(e.target.value)}
              placeholder="Ask about portfolio risk, property ARV, market rates..."
              style={{
                flex: 1, padding: '12px 16px', borderRadius: 10, border: '1px solid #e2e8f0',
                fontSize: 14, outline: 'none'
              }}
            />
            <button type="submit" style={{
              padding: '12px 20px', background: '#7c3aed', color: '#fff', border: 'none',
              borderRadius: 10, cursor: 'pointer', fontWeight: 600
            }}>Send</button>
          </form>
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 24, flexWrap: 'wrap' }}>
        {['dashboard', 'loans', 'applications', 'payments'].map(tab => (
          <button key={tab} onClick={() => setActiveTab(tab)} style={{
            padding: '10px 20px', borderRadius: 10, border: 'none', cursor: 'pointer',
            background: activeTab === tab ? '#0f172a' : '#f1f5f9',
            color: activeTab === tab ? '#fff' : '#475569',
            fontWeight: 600, fontSize: 14, textTransform: 'capitalize'
          }}>{tab}</button>
        ))}
      </div>

      {activeTab === 'dashboard' && (
        <>
          {/* Stats */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16, marginBottom: 28 }}>
            {stats.map((stat, i) => (
              <div key={i} style={{
                background: '#fff', borderRadius: 14, padding: 24,
                boxShadow: '0 2px 12px rgba(0,0,0,0.06)', border: '1px solid #f1f5f9'
              }}>
                <div style={{ fontSize: 28, marginBottom: 8 }}>{stat.icon}</div>
                <div style={{ fontSize: 13, color: '#64748b', fontWeight: 500 }}>{stat.label}</div>
                <div style={{ fontSize: 28, fontWeight: 800, color: '#0f172a', margin: '4px 0' }}>{stat.value}</div>
                <div style={{ fontSize: 12, color: stat.color, fontWeight: 600 }}>{stat.change}</div>
              </div>
            ))}
          </div>

          {/* AI Insights */}
          <div style={{
            background: '#fff', borderRadius: 14, padding: 24, marginBottom: 28,
            boxShadow: '0 2px 12px rgba(0,0,0,0.06)', border: '1px solid #f1f5f9'
          }}>
            <h3 style={{ margin: '0 0 16px', fontSize: 18, fontWeight: 700, color: '#0f172a' }}>🤖 AI Insights</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {aiInsights.map((insight, i) => (
                <div key={i} style={{
                  display: 'flex', alignItems: 'flex-start', gap: 12, padding: '12px 16px',
                  background: insightColors[insight.type], borderRadius: 10
                }}>
                  <span style={{ fontSize: 18 }}>{insightIcons[insight.type]}</span>
                  <span style={{ fontSize: 14, color: '#0f172a', lineHeight: 1.5 }}>{insight.text}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Recent Loans Table */}
          <div style={{
            background: '#fff', borderRadius: 14, padding: 24,
            boxShadow: '0 2px 12px rgba(0,0,0,0.06)', border: '1px solid #f1f5f9'
          }}>
            <h3 style={{ margin: '0 0 16px', fontSize: 18, fontWeight: 700, color: '#0f172a' }}>Recent Loans</h3>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                <thead>
                  <tr style={{ borderBottom: '2px solid #f1f5f9' }}>
                    {['Loan ID', 'Borrower', 'Property', 'Amount', 'LTV', 'Rate', 'Status'].map(h => (
                      <th key={h} style={{ textAlign: 'left', padding: '10px 12px', color: '#64748b', fontWeight: 600, fontSize: 12, textTransform: 'uppercase' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sampleLoans.map(loan => (
                    <tr key={loan.id} style={{ borderBottom: '1px solid #f8fafc' }}>
                      <td style={{ padding: '12px', fontWeight: 600, color: '#2563eb' }}>{loan.id}</td>
                      <td style={{ padding: '12px', color: '#0f172a' }}>{loan.borrower}</td>
                      <td style={{ padding: '12px', color: '#64748b', fontSize: 13 }}>{loan.property}</td>
                      <td style={{ padding: '12px', fontWeight: 600 }}>${loan.amount.toLocaleString()}</td>
                      <td style={{ padding: '12px' }}>{loan.ltv}%</td>
                      <td style={{ padding: '12px' }}>{loan.rate}%</td>
                      <td style={{ padding: '12px' }}>
                        <span style={{
                          padding: '4px 12px', borderRadius: 20, fontSize: 12, fontWeight: 600,
                          background: statusColors[loan.status].bg, color: statusColors[loan.status].text
                        }}>{loan.status}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {activeTab === 'loans' && (
        <div style={{ background: '#fff', borderRadius: 14, padding: 24, boxShadow: '0 2px 12px rgba(0,0,0,0.06)' }}>
          <h3 style={{ margin: '0 0 20px', fontSize: 18, fontWeight: 700 }}>Loan Pipeline</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 16 }}>
            {['Review', 'Active', 'Late', 'Paid Off'].map(status => (
              <div key={status} style={{ background: '#f8fafc', borderRadius: 12, padding: 16 }}>
                <div style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12
                }}>
                  <span style={{
                    padding: '4px 12px', borderRadius: 20, fontSize: 12, fontWeight: 700,
                    background: statusColors[status].bg, color: statusColors[status].text
                  }}>{status}</span>
                  <span style={{ fontSize: 13, color: '#64748b' }}>
                    {sampleLoans.filter(l => l.status === status).length} loans
                  </span>
                </div>
                {sampleLoans.filter(l => l.status === status).map(loan => (
                  <div key={loan.id} style={{
                    background: '#fff', borderRadius: 10, padding: 14, marginBottom: 8,
                    border: '1px solid #e2e8f0'
                  }}>
                    <div style={{ fontWeight: 700, fontSize: 14, color: '#0f172a' }}>{loan.borrower}</div>
                    <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>{loan.property}</div>
                    <div style={{ fontSize: 16, fontWeight: 700, color: '#2563eb', marginTop: 8 }}>${loan.amount.toLocaleString()}</div>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}

      {activeTab === 'applications' && (
        <div style={{ background: '#fff', borderRadius: 14, padding: 32, boxShadow: '0 2px 12px rgba(0,0,0,0.06)' }}>
          <h3 style={{ margin: '0 0 24px', fontSize: 18, fontWeight: 700 }}>New Loan Application</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
            {[
              { label: 'Borrower Name', placeholder: 'Full legal name' },
              { label: 'Email', placeholder: 'borrower@email.com' },
              { label: 'Phone', placeholder: '(555) 123-4567' },
              { label: 'Property Address', placeholder: 'Full property address' },
              { label: 'Purchase Price', placeholder: '$0.00' },
              { label: 'Loan Amount Requested', placeholder: '$0.00' },
              { label: 'Estimated ARV', placeholder: '$0.00' },
              { label: 'Rehab Budget', placeholder: '$0.00' },
            ].map((field, i) => (
              <div key={i}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 6 }}>{field.label}</label>
                <input placeholder={field.placeholder} style={{
                  width: '100%', padding: '10px 14px', borderRadius: 8, border: '1px solid #d1d5db',
                  fontSize: 14, outline: 'none', boxSizing: 'border-box'
                }} />
              </div>
            ))}
          </div>
          <div style={{ marginTop: 20 }}>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 6 }}>Project Description</label>
            <textarea placeholder="Describe the project, exit strategy, borrower experience..." rows={4} style={{
              width: '100%', padding: '10px 14px', borderRadius: 8, border: '1px solid #d1d5db',
              fontSize: 14, outline: 'none', resize: 'vertical', boxSizing: 'border-box'
            }} />
          </div>
          <button style={{
            marginTop: 24, padding: '14px 32px', background: '#1a5c2a', color: '#fff',
            border: 'none', borderRadius: 10, fontWeight: 700, fontSize: 15, cursor: 'pointer'
          }}>Submit Application for AI Review</button>
        </div>
      )}

      {activeTab === 'payments' && (
        <div style={{ background: '#fff', borderRadius: 14, padding: 24, boxShadow: '0 2px 12px rgba(0,0,0,0.06)' }}>
          <h3 style={{ margin: '0 0 20px', fontSize: 18, fontWeight: 700 }}>Payment Tracker</h3>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
              <thead>
                <tr style={{ borderBottom: '2px solid #f1f5f9' }}>
                  {['Loan', 'Borrower', 'Monthly Payment', 'Payments Made', 'Next Due', 'Status'].map(h => (
                    <th key={h} style={{ textAlign: 'left', padding: '10px 12px', color: '#64748b', fontWeight: 600, fontSize: 12, textTransform: 'uppercase' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sampleLoans.filter(l => l.status !== 'Review' && l.status !== 'Paid Off').map(loan => {
                  const monthly = Math.round((loan.amount * (loan.rate / 100)) / 12);
                  return (
                    <tr key={loan.id} style={{ borderBottom: '1px solid #f8fafc' }}>
                      <td style={{ padding: '12px', fontWeight: 600, color: '#2563eb' }}>{loan.id}</td>
                      <td style={{ padding: '12px' }}>{loan.borrower}</td>
                      <td style={{ padding: '12px', fontWeight: 600 }}>${monthly.toLocaleString()}</td>
                      <td style={{ padding: '12px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <div style={{ flex: 1, height: 6, background: '#f1f5f9', borderRadius: 3 }}>
                            <div style={{
                              height: '100%', borderRadius: 3, background: loan.status === 'Late' ? '#ef4444' : '#22c55e',
                              width: `${(loan.payments / loan.term) * 100}%`
                            }} />
                          </div>
                          <span style={{ fontSize: 12, color: '#64748b' }}>{loan.payments}/{loan.term}</span>
                        </div>
                      </td>
                      <td style={{ padding: '12px', fontSize: 13 }}>Apr 1, 2024</td>
                      <td style={{ padding: '12px' }}>
                        <span style={{
                          padding: '4px 12px', borderRadius: 20, fontSize: 12, fontWeight: 600,
                          background: loan.status === 'Late' ? '#fee2e2' : '#dcfce7',
                          color: loan.status === 'Late' ? '#991b1b' : '#166534'
                        }}>{loan.status === 'Late' ? 'Past Due' : 'Current'}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Demo Badge */}
      <div style={{
        textAlign: 'center', marginTop: 40, padding: '16px',
        background: '#f8fafc', borderRadius: 10, fontSize: 13, color: '#94a3b8'
      }}>
        DEMO MODE — Sample data shown for demonstration purposes
      </div>
    </div>
  );
}
