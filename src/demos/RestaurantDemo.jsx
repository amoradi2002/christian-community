import React, { useState } from 'react';
import { Link } from 'react-router-dom';

const menuItems = [
  { id: 1, name: 'Classic Burger', category: 'Mains', price: 14.99, sold: 145, popular: true },
  { id: 2, name: 'Caesar Salad', category: 'Starters', price: 10.99, sold: 89, popular: false },
  { id: 3, name: 'Grilled Salmon', category: 'Mains', price: 22.99, sold: 112, popular: true },
  { id: 4, name: 'Margherita Pizza', category: 'Mains', price: 16.99, sold: 198, popular: true },
  { id: 5, name: 'Wings (12pc)', category: 'Starters', price: 13.99, sold: 167, popular: true },
  { id: 6, name: 'Chocolate Lava Cake', category: 'Desserts', price: 9.99, sold: 78, popular: false },
  { id: 7, name: 'Loaded Fries', category: 'Sides', price: 8.99, sold: 201, popular: true },
  { id: 8, name: 'Iced Tea', category: 'Drinks', price: 3.99, sold: 312, popular: false },
];

const orders = [
  { id: '#1247', customer: 'Table 5', items: 3, total: 47.97, status: 'Preparing', time: '2 min ago' },
  { id: '#1246', customer: 'Online - Mike R.', items: 2, total: 31.98, status: 'Ready', time: '8 min ago' },
  { id: '#1245', customer: 'Table 2', items: 5, total: 82.95, status: 'Served', time: '15 min ago' },
  { id: '#1244', customer: 'Online - Sarah L.', items: 1, total: 16.99, status: 'Delivering', time: '20 min ago' },
  { id: '#1243', customer: 'Table 8', items: 4, total: 64.96, status: 'Served', time: '25 min ago' },
];

const reservations = [
  { name: 'Johnson Party', size: 6, time: '6:00 PM', status: 'Confirmed', notes: 'Birthday celebration' },
  { name: 'Chen Family', size: 4, time: '6:30 PM', status: 'Confirmed', notes: '' },
  { name: 'Martinez', size: 2, time: '7:00 PM', status: 'Waitlisted', notes: 'Prefers outdoor seating' },
  { name: 'Williams Group', size: 8, time: '7:30 PM', status: 'Confirmed', notes: 'Business dinner, need private area' },
  { name: 'Davis', size: 2, time: '8:00 PM', status: 'Confirmed', notes: 'Anniversary, request window table' },
];

const orderStatusColors = {
  Preparing: { bg: '#fef3c7', text: '#92400e' },
  Ready: { bg: '#dcfce7', text: '#166534' },
  Served: { bg: '#dbeafe', text: '#1e40af' },
  Delivering: { bg: '#ede9fe', text: '#5b21b6' },
  Confirmed: { bg: '#dcfce7', text: '#166534' },
  Waitlisted: { bg: '#fef3c7', text: '#92400e' },
};

const restaurantStats = [
  { label: "Today's Revenue", value: '$3,847', icon: '💰', sub: '+18% vs last Monday' },
  { label: 'Orders Today', value: '67', icon: '🧾', sub: '12 online, 55 dine-in' },
  { label: 'Reservations Tonight', value: '5', icon: '📅', sub: '22 guests expected' },
  { label: 'Top Seller', value: 'Loaded Fries', icon: '🔥', sub: '201 sold this week' },
];

export default function RestaurantDemo() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [showAI, setShowAI] = useState(false);
  const [aiChat, setAiChat] = useState('');
  const [chatMessages, setChatMessages] = useState([
    { role: 'ai', text: "Hey chef! I'm your AI restaurant assistant. I can help with menu optimization, inventory forecasting, staffing suggestions, and revenue insights." }
  ]);

  const handleChat = (e) => {
    e.preventDefault();
    if (!aiChat.trim()) return;
    const userMsg = aiChat;
    setChatMessages(prev => [...prev, { role: 'user', text: userMsg }]);
    setAiChat('');
    setTimeout(() => {
      let response = "Today's looking strong — revenue is up 18% vs last Monday. You've got 5 reservations tonight (22 guests). I'd recommend having an extra server on the floor from 6-8 PM to handle the rush. Also, Loaded Fries are outselling everything — consider making it a featured item.";
      if (userMsg.toLowerCase().includes('menu') || userMsg.toLowerCase().includes('price')) {
        response = "Menu optimization suggestions:\n\n1. Loaded Fries ($8.99) — highest volume item with 73% margin. Consider a $1 price increase, customers won't blink.\n2. Chocolate Lava Cake ($9.99) — underselling at 78 units. Try offering it as a $5 add-on with any main to boost dessert attach rate.\n3. Caesar Salad ($10.99) — lowest seller in starters. Consider updating the recipe or replacing with a trending item like a burrata salad.";
      } else if (userMsg.toLowerCase().includes('staff') || userMsg.toLowerCase().includes('schedule')) {
        response = "Based on this week's reservation data and historical trends:\n\n• Mon-Wed: 2 servers + 1 cook minimum\n• Thu: 3 servers + 2 cooks (trivia night draws +40% traffic)\n• Fri-Sat: 4 servers + 3 cooks (peak nights)\n• Sun: 3 servers + 2 cooks (brunch crowd)\n\nYou could save ~$400/week by reducing Tuesday staffing by 1 server — it's consistently your slowest day.";
      } else if (userMsg.toLowerCase().includes('inventory') || userMsg.toLowerCase().includes('order')) {
        response = "Inventory forecast for this week:\n\n⚠️ Low stock alerts:\n• Ground beef — ~2 days left at current rate. Order 40lbs by Wednesday.\n• Salmon — 8 portions left. Order 20 fillets ASAP.\n• Fry oil — running low, order 2 cases.\n\n✅ Well stocked: Produce, beverages, dessert supplies\n\nEstimated food cost this week: $2,100 (target: $2,000). The salmon price went up 12% — consider a temporary $2 menu increase.";
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
            🍽️ Savory Kitchen & Bar
          </h1>
          <p style={{ color: '#64748b', margin: '4px 0 0', fontSize: 14 }}>Restaurant Management System</p>
        </div>
        <button
          onClick={() => setShowAI(!showAI)}
          style={{
            padding: '12px 24px', background: 'linear-gradient(135deg, #dc2626, #ea580c)',
            color: '#fff', border: 'none', borderRadius: 12, cursor: 'pointer',
            fontWeight: 700, fontSize: 14, boxShadow: '0 4px 14px rgba(220,38,38,0.3)'
          }}
        >
          {showAI ? '✕ Close AI Assistant' : '🤖 AI Assistant'}
        </button>
      </div>

      {/* AI Chat */}
      {showAI && (
        <div style={{
          background: '#fff', borderRadius: 16, padding: 24, marginBottom: 24,
          border: '2px solid #dc2626', boxShadow: '0 8px 30px rgba(220,38,38,0.15)'
        }}>
          <h3 style={{ margin: '0 0 16px', color: '#dc2626', fontSize: 16 }}>🤖 AI Restaurant Assistant</h3>
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
                  background: msg.role === 'user' ? '#dc2626' : '#fff',
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
              placeholder="Try: 'Menu optimization' or 'Staffing schedule' or 'Inventory forecast'"
              style={{
                flex: 1, padding: '12px 16px', borderRadius: 10, border: '1px solid #e2e8f0',
                fontSize: 14, outline: 'none'
              }}
            />
            <button type="submit" style={{
              padding: '12px 20px', background: '#dc2626', color: '#fff', border: 'none',
              borderRadius: 10, cursor: 'pointer', fontWeight: 600
            }}>Send</button>
          </form>
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 24, flexWrap: 'wrap' }}>
        {['dashboard', 'menu', 'orders', 'reservations'].map(tab => (
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
            {restaurantStats.map((stat, i) => (
              <div key={i} style={{
                background: '#fff', borderRadius: 14, padding: 24,
                boxShadow: '0 2px 12px rgba(0,0,0,0.06)', border: '1px solid #f1f5f9'
              }}>
                <div style={{ fontSize: 28, marginBottom: 8 }}>{stat.icon}</div>
                <div style={{ fontSize: 13, color: '#64748b', fontWeight: 500 }}>{stat.label}</div>
                <div style={{ fontSize: 24, fontWeight: 800, color: '#0f172a', margin: '4px 0' }}>{stat.value}</div>
                <div style={{ fontSize: 12, color: '#64748b' }}>{stat.sub}</div>
              </div>
            ))}
          </div>

          {/* Orders + Reservations */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
            <div style={{
              background: '#fff', borderRadius: 14, padding: 24,
              boxShadow: '0 2px 12px rgba(0,0,0,0.06)', border: '1px solid #f1f5f9'
            }}>
              <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 700 }}>Live Orders</h3>
              {orders.map(o => (
                <div key={o.id} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '10px 0', borderBottom: '1px solid #f1f5f9'
                }}>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 14 }}>{o.id} — {o.customer}</div>
                    <div style={{ fontSize: 12, color: '#64748b' }}>{o.items} items &bull; {o.time}</div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontWeight: 700, fontSize: 14 }}>${o.total.toFixed(2)}</div>
                    <span style={{
                      padding: '2px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600,
                      background: orderStatusColors[o.status].bg, color: orderStatusColors[o.status].text
                    }}>{o.status}</span>
                  </div>
                </div>
              ))}
            </div>

            <div style={{
              background: '#fff', borderRadius: 14, padding: 24,
              boxShadow: '0 2px 12px rgba(0,0,0,0.06)', border: '1px solid #f1f5f9'
            }}>
              <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 700 }}>Tonight's Reservations</h3>
              {reservations.map((r, i) => (
                <div key={i} style={{
                  padding: '10px 0', borderBottom: '1px solid #f1f5f9'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ fontWeight: 600, fontSize: 14 }}>{r.name}</div>
                    <span style={{
                      padding: '2px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600,
                      background: orderStatusColors[r.status].bg, color: orderStatusColors[r.status].text
                    }}>{r.status}</span>
                  </div>
                  <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>
                    {r.time} &bull; Party of {r.size} {r.notes && `&bull; ${r.notes}`}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {activeTab === 'menu' && (
        <div style={{
          background: '#fff', borderRadius: 14, padding: 24,
          boxShadow: '0 2px 12px rgba(0,0,0,0.06)', border: '1px solid #f1f5f9'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
            <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>Menu Items</h3>
            <button style={{
              padding: '8px 20px', background: '#dc2626', color: '#fff', border: 'none',
              borderRadius: 8, fontWeight: 600, cursor: 'pointer', fontSize: 13
            }}>+ Add Item</button>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
              <thead>
                <tr style={{ borderBottom: '2px solid #f1f5f9' }}>
                  {['Item', 'Category', 'Price', 'Sold This Week', 'Status'].map(h => (
                    <th key={h} style={{ textAlign: 'left', padding: '10px 12px', color: '#64748b', fontWeight: 600, fontSize: 12, textTransform: 'uppercase' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {menuItems.map(item => (
                  <tr key={item.id} style={{ borderBottom: '1px solid #f8fafc' }}>
                    <td style={{ padding: '12px', fontWeight: 600, color: '#0f172a' }}>{item.name}</td>
                    <td style={{ padding: '12px', color: '#64748b' }}>{item.category}</td>
                    <td style={{ padding: '12px', fontWeight: 600 }}>${item.price.toFixed(2)}</td>
                    <td style={{ padding: '12px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div style={{ flex: 1, maxWidth: 100, height: 6, background: '#f1f5f9', borderRadius: 3 }}>
                          <div style={{
                            height: '100%', borderRadius: 3, background: '#dc2626',
                            width: `${Math.min((item.sold / 312) * 100, 100)}%`
                          }} />
                        </div>
                        <span style={{ fontSize: 13, color: '#0f172a', fontWeight: 600 }}>{item.sold}</span>
                      </div>
                    </td>
                    <td style={{ padding: '12px' }}>
                      {item.popular && (
                        <span style={{
                          padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 700,
                          background: '#fef3c7', color: '#92400e'
                        }}>Popular</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {activeTab === 'orders' && (
        <div style={{
          background: '#fff', borderRadius: 14, padding: 24,
          boxShadow: '0 2px 12px rgba(0,0,0,0.06)', border: '1px solid #f1f5f9'
        }}>
          <h3 style={{ margin: '0 0 20px', fontSize: 18, fontWeight: 700 }}>Order Queue</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 16 }}>
            {['Preparing', 'Ready', 'Delivering', 'Served'].map(status => (
              <div key={status} style={{ background: '#f8fafc', borderRadius: 12, padding: 16 }}>
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12
                }}>
                  <span style={{
                    padding: '4px 12px', borderRadius: 20, fontSize: 12, fontWeight: 700,
                    background: orderStatusColors[status].bg, color: orderStatusColors[status].text
                  }}>{status}</span>
                </div>
                {orders.filter(o => o.status === status).map(o => (
                  <div key={o.id} style={{
                    background: '#fff', borderRadius: 10, padding: 14, marginBottom: 8,
                    border: '1px solid #e2e8f0'
                  }}>
                    <div style={{ fontWeight: 700, fontSize: 15 }}>{o.id}</div>
                    <div style={{ fontSize: 13, color: '#64748b', marginTop: 2 }}>{o.customer}</div>
                    <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 2 }}>{o.items} items &bull; {o.time}</div>
                    <div style={{ fontWeight: 700, color: '#dc2626', marginTop: 6 }}>${o.total.toFixed(2)}</div>
                  </div>
                ))}
                {orders.filter(o => o.status === status).length === 0 && (
                  <div style={{ color: '#94a3b8', fontSize: 13, textAlign: 'center', padding: 20 }}>No orders</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {activeTab === 'reservations' && (
        <div style={{
          background: '#fff', borderRadius: 14, padding: 32,
          boxShadow: '0 2px 12px rgba(0,0,0,0.06)', border: '1px solid #f1f5f9'
        }}>
          <h3 style={{ margin: '0 0 24px', fontSize: 18, fontWeight: 700 }}>Make a Reservation</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
            {[
              { label: 'Guest Name', placeholder: 'Full name' },
              { label: 'Phone Number', placeholder: '(555) 123-4567' },
              { label: 'Party Size', placeholder: 'Number of guests' },
              { label: 'Date', placeholder: 'MM/DD/YYYY' },
              { label: 'Time', placeholder: 'Preferred time' },
              { label: 'Email', placeholder: 'guest@email.com' },
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
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 6 }}>Special Requests</label>
            <textarea placeholder="Dietary restrictions, celebrations, seating preferences..." rows={3} style={{
              width: '100%', padding: '10px 14px', borderRadius: 8, border: '1px solid #d1d5db',
              fontSize: 14, outline: 'none', resize: 'vertical', boxSizing: 'border-box'
            }} />
          </div>
          <button style={{
            marginTop: 24, padding: '14px 32px', background: '#dc2626', color: '#fff',
            border: 'none', borderRadius: 10, fontWeight: 700, fontSize: 15, cursor: 'pointer'
          }}>Reserve Table</button>
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
