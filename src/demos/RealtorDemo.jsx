import React, { useState } from 'react';
import { Link } from 'react-router-dom';

const listings = [
  { id: 1, address: '4521 Magnolia Blvd', city: 'Houston, TX', price: 425000, beds: 4, baths: 3, sqft: 2800, status: 'Active', days: 5, image: '🏡' },
  { id: 2, address: '789 Sunset Dr', city: 'Dallas, TX', price: 315000, beds: 3, baths: 2, sqft: 1950, status: 'Pending', days: 12, image: '🏠' },
  { id: 3, address: '1100 Lakewood Ct', city: 'Austin, TX', price: 589000, beds: 5, baths: 4, sqft: 3400, status: 'Active', days: 2, image: '🏘️' },
  { id: 4, address: '332 River Oak Ln', city: 'San Antonio, TX', price: 275000, beds: 3, baths: 2, sqft: 1650, status: 'Active', days: 8, image: '🏡' },
  { id: 5, address: '2200 Heritage Pkwy', city: 'Fort Worth, TX', price: 498000, beds: 4, baths: 3, sqft: 2950, status: 'Sold', days: 0, image: '🏠' },
  { id: 6, address: '915 Willow Creek', city: 'Plano, TX', price: 365000, beds: 3, baths: 2, sqft: 2100, status: 'Active', days: 15, image: '🏘️' },
];

const leads = [
  { name: 'Michael Rivera', type: 'Buyer', budget: '$300-400K', status: 'Hot', lastContact: '2 hours ago', notes: 'Looking for 3+ bed in Dallas area. Pre-approved.' },
  { name: 'Lisa Chang', type: 'Seller', budget: '$450K', status: 'Hot', lastContact: '1 day ago', notes: 'Wants to list 4521 Magnolia. Motivated seller, relocating.' },
  { name: 'James & Kim Park', type: 'Buyer', budget: '$500-600K', status: 'Warm', lastContact: '3 days ago', notes: 'First-time buyers. Interested in Austin suburbs.' },
  { name: 'Diane Cooper', type: 'Seller', budget: '$280K', status: 'Warm', lastContact: '5 days ago', notes: 'Inherited property. Needs renovation assessment.' },
  { name: 'Tom Bradley', type: 'Buyer', budget: '$200-300K', status: 'Cold', lastContact: '2 weeks ago', notes: 'Investment buyer. Looking for fix-and-flip opportunities.' },
  { name: 'Sandra Hughes', type: 'Buyer', budget: '$350-450K', status: 'New', lastContact: 'Just now', notes: 'Came through website chatbot. Wants to schedule showing.' },
];

const statusColors = {
  Active: { bg: '#dcfce7', text: '#166534' },
  Pending: { bg: '#fef3c7', text: '#92400e' },
  Sold: { bg: '#dbeafe', text: '#1e40af' },
  Hot: { bg: '#fee2e2', text: '#991b1b' },
  Warm: { bg: '#fef3c7', text: '#92400e' },
  Cold: { bg: '#f1f5f9', text: '#475569' },
  New: { bg: '#ede9fe', text: '#5b21b6' },
};

const realtorStats = [
  { label: 'Active Listings', value: '4', icon: '🏠', color: '#059669' },
  { label: 'Total Volume', value: '$2.47M', icon: '💰', color: '#2563eb' },
  { label: 'Hot Leads', value: '2', icon: '🔥', color: '#dc2626' },
  { label: 'Avg Days on Market', value: '7.5', icon: '📅', color: '#7c3aed' },
];

export default function RealtorDemo() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [showAI, setShowAI] = useState(false);
  const [aiChat, setAiChat] = useState('');
  const [chatMessages, setChatMessages] = useState([
    { role: 'ai', text: "Hey! I'm your AI real estate assistant. I can generate listing descriptions, analyze comps, qualify leads, and help with market insights." }
  ]);

  const handleChat = (e) => {
    e.preventDefault();
    if (!aiChat.trim()) return;
    const userMsg = aiChat;
    setChatMessages(prev => [...prev, { role: 'user', text: userMsg }]);
    setAiChat('');
    setTimeout(() => {
      let response = "Looking at your current portfolio, you have 4 active listings with a combined value of $1.65M. 789 Sunset Dr just went pending — congrats! Your hottest lead Sandra Hughes came through the website chatbot and wants a showing. I'd prioritize her and Michael Rivera today.";
      if (userMsg.toLowerCase().includes('description') || userMsg.toLowerCase().includes('listing')) {
        response = "Here's a generated listing description for 4521 Magnolia Blvd:\n\n\"Stunning 4-bedroom, 3-bath home in the heart of Houston. This 2,800 sqft beauty features an open-concept layout, gourmet kitchen with granite countertops, and a spacious primary suite. Recently updated with modern finishes throughout. Large backyard perfect for entertaining. Minutes from top-rated schools and dining. Don't miss this one — schedule your showing today!\"";
      } else if (userMsg.toLowerCase().includes('comp') || userMsg.toLowerCase().includes('price')) {
        response = "Running comps for the Houston area (77004 zip):\n\n• 4BR/3BA homes sold in last 90 days: 12 properties\n• Average sale price: $418,000\n• Price per sqft: $148-162\n• Average days on market: 14\n\nYour listing at $425K ($151/sqft) is priced competitively. I'd hold firm for the first 2 weeks, then consider a $10K reduction if showings slow down.";
      } else if (userMsg.toLowerCase().includes('lead') || userMsg.toLowerCase().includes('follow')) {
        response = "Lead priority list for today:\n\n1. 🔥 Sandra Hughes (NEW) — Just came in through chatbot. Send intro text + schedule showing ASAP\n2. 🔥 Michael Rivera — Pre-approved buyer, budget fits 3 of your listings. Send him 332 River Oak & 915 Willow Creek\n3. Lisa Chang — Motivated seller, send listing agreement for signature\n4. James & Kim Park — Follow up on Austin properties they viewed last week";
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
            🏠 Premier Realty Group
          </h1>
          <p style={{ color: '#64748b', margin: '4px 0 0', fontSize: 14 }}>Real Estate CRM & Listing Management</p>
        </div>
        <button
          onClick={() => setShowAI(!showAI)}
          style={{
            padding: '12px 24px', background: 'linear-gradient(135deg, #2563eb, #0ea5e9)',
            color: '#fff', border: 'none', borderRadius: 12, cursor: 'pointer',
            fontWeight: 700, fontSize: 14, boxShadow: '0 4px 14px rgba(37,99,235,0.3)'
          }}
        >
          {showAI ? '✕ Close AI Assistant' : '🤖 AI Assistant'}
        </button>
      </div>

      {/* AI Chat */}
      {showAI && (
        <div style={{
          background: '#fff', borderRadius: 16, padding: 24, marginBottom: 24,
          border: '2px solid #2563eb', boxShadow: '0 8px 30px rgba(37,99,235,0.15)'
        }}>
          <h3 style={{ margin: '0 0 16px', color: '#2563eb', fontSize: 16 }}>🤖 AI Real Estate Assistant</h3>
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
                  fontSize: 14, lineHeight: 1.6, whiteSpace: 'pre-line',
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
              placeholder="Try: 'Write a listing description' or 'Run comps' or 'Lead priorities'"
              style={{
                flex: 1, padding: '12px 16px', borderRadius: 10, border: '1px solid #e2e8f0',
                fontSize: 14, outline: 'none'
              }}
            />
            <button type="submit" style={{
              padding: '12px 20px', background: '#2563eb', color: '#fff', border: 'none',
              borderRadius: 10, cursor: 'pointer', fontWeight: 600
            }}>Send</button>
          </form>
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 24, flexWrap: 'wrap' }}>
        {['dashboard', 'listings', 'leads', 'analytics'].map(tab => (
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
            {realtorStats.map((stat, i) => (
              <div key={i} style={{
                background: '#fff', borderRadius: 14, padding: 24,
                boxShadow: '0 2px 12px rgba(0,0,0,0.06)', border: '1px solid #f1f5f9'
              }}>
                <div style={{ fontSize: 28, marginBottom: 8 }}>{stat.icon}</div>
                <div style={{ fontSize: 13, color: '#64748b', fontWeight: 500 }}>{stat.label}</div>
                <div style={{ fontSize: 28, fontWeight: 800, color: '#0f172a', margin: '4px 0' }}>{stat.value}</div>
              </div>
            ))}
          </div>

          {/* Listings + Leads side by side */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
            <div style={{
              background: '#fff', borderRadius: 14, padding: 24,
              boxShadow: '0 2px 12px rgba(0,0,0,0.06)', border: '1px solid #f1f5f9'
            }}>
              <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 700 }}>Recent Listings</h3>
              {listings.slice(0, 4).map(l => (
                <div key={l.id} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '12px 0', borderBottom: '1px solid #f1f5f9'
                }}>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 14, color: '#0f172a' }}>{l.address}</div>
                    <div style={{ fontSize: 12, color: '#64748b' }}>{l.city} &bull; {l.beds}bd/{l.baths}ba &bull; {l.sqft.toLocaleString()} sqft</div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontWeight: 700, color: '#2563eb' }}>${l.price.toLocaleString()}</div>
                    <span style={{
                      padding: '2px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600,
                      background: statusColors[l.status].bg, color: statusColors[l.status].text
                    }}>{l.status}</span>
                  </div>
                </div>
              ))}
            </div>

            <div style={{
              background: '#fff', borderRadius: 14, padding: 24,
              boxShadow: '0 2px 12px rgba(0,0,0,0.06)', border: '1px solid #f1f5f9'
            }}>
              <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 700 }}>Hot Leads</h3>
              {leads.filter(l => l.status === 'Hot' || l.status === 'New').map((lead, i) => (
                <div key={i} style={{
                  padding: '12px 0', borderBottom: '1px solid #f1f5f9'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ fontWeight: 600, fontSize: 14 }}>{lead.name}</div>
                    <span style={{
                      padding: '2px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600,
                      background: statusColors[lead.status].bg, color: statusColors[lead.status].text
                    }}>{lead.status}</span>
                  </div>
                  <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>{lead.type} &bull; {lead.budget} &bull; {lead.lastContact}</div>
                  <div style={{ fontSize: 12, color: '#475569', marginTop: 4 }}>{lead.notes}</div>
                </div>
              ))}
            </div>
          </div>

          {/* AI Website Chatbot Preview */}
          <div style={{
            background: '#fff', borderRadius: 14, padding: 24, marginTop: 20,
            boxShadow: '0 2px 12px rgba(0,0,0,0.06)', border: '1px solid #f1f5f9'
          }}>
            <h3 style={{ margin: '0 0 4px', fontSize: 16, fontWeight: 700 }}>🤖 Website AI Chatbot Preview</h3>
            <p style={{ fontSize: 13, color: '#64748b', marginTop: 0 }}>This chatbot lives on your website and captures leads 24/7</p>
            <div style={{
              background: '#f8fafc', borderRadius: 12, padding: 20, marginTop: 12, maxWidth: 400
            }}>
              <div style={{ background: '#2563eb', color: '#fff', padding: '10px 16px', borderRadius: '12px 12px 12px 2px', fontSize: 14, marginBottom: 10 }}>
                Hi! Welcome to Premier Realty Group. I can help you find your dream home, schedule a showing, or get a free home valuation. What are you looking for?
              </div>
              <div style={{ background: '#e2e8f0', padding: '10px 16px', borderRadius: '12px 12px 2px 12px', fontSize: 14, marginBottom: 10, marginLeft: 'auto', maxWidth: '80%', textAlign: 'right' }}>
                I'm looking for a 3 bedroom house in Dallas under $400K
              </div>
              <div style={{ background: '#2563eb', color: '#fff', padding: '10px 16px', borderRadius: '12px 12px 12px 2px', fontSize: 14 }}>
                Great choice! We have 2 properties that match: 789 Sunset Dr ($315K, 3bd/2ba) and 915 Willow Creek ($365K, 3bd/2ba). Would you like to schedule a showing? I can also connect you with our agent!
              </div>
            </div>
          </div>
        </>
      )}

      {activeTab === 'listings' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 20 }}>
          {listings.map(l => (
            <div key={l.id} style={{
              background: '#fff', borderRadius: 14, overflow: 'hidden',
              boxShadow: '0 2px 12px rgba(0,0,0,0.06)', border: '1px solid #f1f5f9'
            }}>
              <div style={{
                height: 160, background: 'linear-gradient(135deg, #e0f2fe, #dbeafe)',
                display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 64
              }}>{l.image}</div>
              <div style={{ padding: 20 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{
                    padding: '4px 12px', borderRadius: 20, fontSize: 11, fontWeight: 700,
                    background: statusColors[l.status].bg, color: statusColors[l.status].text
                  }}>{l.status}</span>
                  {l.days > 0 && <span style={{ fontSize: 12, color: '#64748b' }}>{l.days} days on market</span>}
                </div>
                <h3 style={{ margin: '12px 0 4px', fontSize: 18, fontWeight: 700, color: '#0f172a' }}>{l.address}</h3>
                <p style={{ margin: 0, fontSize: 14, color: '#64748b' }}>{l.city}</p>
                <div style={{ fontSize: 24, fontWeight: 800, color: '#2563eb', margin: '12px 0' }}>${l.price.toLocaleString()}</div>
                <div style={{ display: 'flex', gap: 16, fontSize: 13, color: '#64748b' }}>
                  <span>{l.beds} beds</span>
                  <span>{l.baths} baths</span>
                  <span>{l.sqft.toLocaleString()} sqft</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {activeTab === 'leads' && (
        <div style={{
          background: '#fff', borderRadius: 14, padding: 24,
          boxShadow: '0 2px 12px rgba(0,0,0,0.06)', border: '1px solid #f1f5f9'
        }}>
          <h3 style={{ margin: '0 0 20px', fontSize: 18, fontWeight: 700 }}>Lead Pipeline</h3>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
              <thead>
                <tr style={{ borderBottom: '2px solid #f1f5f9' }}>
                  {['Name', 'Type', 'Budget', 'Status', 'Last Contact', 'Notes'].map(h => (
                    <th key={h} style={{ textAlign: 'left', padding: '10px 12px', color: '#64748b', fontWeight: 600, fontSize: 12, textTransform: 'uppercase' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {leads.map((lead, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid #f8fafc' }}>
                    <td style={{ padding: '12px', fontWeight: 600, color: '#0f172a' }}>{lead.name}</td>
                    <td style={{ padding: '12px' }}>
                      <span style={{
                        padding: '3px 10px', borderRadius: 20, fontSize: 12, fontWeight: 600,
                        background: lead.type === 'Buyer' ? '#dbeafe' : '#fce7f3',
                        color: lead.type === 'Buyer' ? '#1e40af' : '#9d174d'
                      }}>{lead.type}</span>
                    </td>
                    <td style={{ padding: '12px', fontWeight: 600 }}>{lead.budget}</td>
                    <td style={{ padding: '12px' }}>
                      <span style={{
                        padding: '3px 10px', borderRadius: 20, fontSize: 12, fontWeight: 600,
                        background: statusColors[lead.status].bg, color: statusColors[lead.status].text
                      }}>{lead.status}</span>
                    </td>
                    <td style={{ padding: '12px', fontSize: 13, color: '#64748b' }}>{lead.lastContact}</td>
                    <td style={{ padding: '12px', fontSize: 13, color: '#475569', maxWidth: 250 }}>{lead.notes}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {activeTab === 'analytics' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
          <div style={{
            background: '#fff', borderRadius: 14, padding: 24,
            boxShadow: '0 2px 12px rgba(0,0,0,0.06)', border: '1px solid #f1f5f9'
          }}>
            <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 700 }}>Monthly Performance</h3>
            {[
              { month: 'January', sold: 2, volume: '$640K' },
              { month: 'February', sold: 3, volume: '$920K' },
              { month: 'March', sold: 1, volume: '$498K' },
            ].map((m, i) => (
              <div key={i} style={{
                display: 'flex', justifyContent: 'space-between', padding: '12px 0',
                borderBottom: '1px solid #f1f5f9'
              }}>
                <span style={{ fontWeight: 600 }}>{m.month}</span>
                <span style={{ color: '#64748b' }}>{m.sold} sold</span>
                <span style={{ fontWeight: 700, color: '#059669' }}>{m.volume}</span>
              </div>
            ))}
            <div style={{
              display: 'flex', justifyContent: 'space-between', padding: '16px 0 0',
              fontWeight: 700, fontSize: 16
            }}>
              <span>YTD Total</span>
              <span style={{ color: '#2563eb' }}>$2.06M</span>
            </div>
          </div>

          <div style={{
            background: '#fff', borderRadius: 14, padding: 24,
            boxShadow: '0 2px 12px rgba(0,0,0,0.06)', border: '1px solid #f1f5f9'
          }}>
            <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 700 }}>Lead Sources</h3>
            {[
              { source: 'Website Chatbot (AI)', pct: 35, color: '#2563eb' },
              { source: 'Referrals', pct: 28, color: '#059669' },
              { source: 'Zillow/Realtor.com', pct: 20, color: '#7c3aed' },
              { source: 'Social Media', pct: 12, color: '#ea580c' },
              { source: 'Walk-ins', pct: 5, color: '#64748b' },
            ].map((s, i) => (
              <div key={i} style={{ marginBottom: 14 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4, fontSize: 13 }}>
                  <span style={{ fontWeight: 600 }}>{s.source}</span>
                  <span style={{ color: '#64748b' }}>{s.pct}%</span>
                </div>
                <div style={{ height: 8, background: '#f1f5f9', borderRadius: 4 }}>
                  <div style={{ height: '100%', width: `${s.pct}%`, background: s.color, borderRadius: 4 }} />
                </div>
              </div>
            ))}
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
