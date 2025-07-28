import React from 'react';
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import './App.css';

// Simple brown cross SVG as a React component
const BrownCross = () => (
  <svg width="60" height="60" viewBox="0 0 60 60" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect x="25" y="5" width="10" height="50" rx="3" fill="#8B5C2A"/>
    <rect x="10" y="25" width="40" height="10" rx="3" fill="#8B5C2A"/>
  </svg>
);

// Array of daily verses
const dailyVerses = [
  { ref: "Philippians 4:13", text: "I can do all this through him who gives me strength." },
  { ref: "Psalm 23:1", text: "The Lord is my shepherd, I lack nothing." },
  { ref: "Proverbs 3:5", text: "Trust in the Lord with all your heart and lean not on your own understanding." },
  { ref: "Isaiah 41:10", text: "Do not fear, for I am with you; do not be dismayed, for I am your God." },
  { ref: "Romans 8:28", text: "And we know that in all things God works for the good of those who love him." },
  { ref: "Matthew 6:33", text: "But seek first his kingdom and his righteousness, and all these things will be given to you as well." },
  { ref: "Joshua 1:9", text: "Be strong and courageous. Do not be afraid; do not be discouraged, for the Lord your God will be with you wherever you go." },
  { ref: "John 3:16", text: "For God so loved the world that he gave his one and only Son, that whoever believes in him shall not perish but have eternal life." },
  { ref: "1 Peter 5:7", text: "Cast all your anxiety on him because he cares for you." },
  { ref: "Jeremiah 29:11", text: "For I know the plans I have for you, declares the Lord, plans to prosper you and not to harm you, plans to give you hope and a future." }
];

// Function to get today's verse
function getDailyVerse() {
  const today = new Date();
  const start = new Date(today.getFullYear(), 0, 0);
  const diff = today - start;
  const oneDay = 1000 * 60 * 60 * 24;
  const dayOfYear = Math.floor(diff / oneDay);
  return dailyVerses[dayOfYear % dailyVerses.length];
}

function Home() {
  const dailyVerse = getDailyVerse();

  // Quick feature cards data
  const features = [
    {
      title: "Life Groups",
      icon: "🤝",
      description: "Find and join a local group to grow in faith together.",
      link: "/life-groups"
    },
    {
      title: "Bible Discussions",
      icon: "📖",
      description: "Share insights and questions about the Bible.",
      link: "/bible-discussions"
    },
    {
      title: "Bible Versions",
      icon: "📚",
      description: "Explore different translations of the Bible.",
      link: "/bible-versions"
    },
    {
      title: "Testimonies",
      icon: "💬",
      description: "Read and share stories of faith and transformation.",
      link: "/testimonies"
    },
    {
      title: "Prayer Wall",
      icon: "🙏",
      description: "Share prayer requests and encourage others.",
      link: "/prayer-wall"
    },
    {
      title: "Music Forum",
      icon: "🎵",
      description: "Share your favorite Christian music and songs.",
      link: "/music-forum"
    }
  ];

  return (
    <div>
      {/* Welcome Banner */}
      <div style={{
        background: '#ffe4b5',
        color: '#8B5C2A',
        borderRadius: 12,
        padding: 24,
        marginBottom: 24,
        boxShadow: '0 1px 6px #e2cfa1',
        textAlign: 'center',
        fontWeight: 700,
        fontSize: 24
      }}>
        Welcome to our Christian Community! <br />
        <span style={{ fontWeight: 400, fontSize: 18 }}>
          A place to connect, grow, and encourage one another in Christ.
        </span>
      </div>

      {/* Daily Verse Card */}
      <div style={{
        background: '#fffbe6',
        color: '#8B5C2A',
        borderRadius: 10,
        padding: 18,
        marginBottom: 32,
        boxShadow: '0 1px 4px #e2cfa1',
        fontWeight: 600,
        fontSize: 18,
        textAlign: 'center'
      }}>
        <span>Daily Verse: <strong>{dailyVerse.ref}</strong> — {dailyVerse.text}</span>
      </div>

      {/* Feature Cards */}
      <div style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: 24,
        justifyContent: 'center',
        marginBottom: 32
      }}>
        {features.map((feature, idx) => (
          <Link
            to={feature.link}
            key={idx}
            style={{
              textDecoration: 'none',
              color: '#8B5C2A',
              background: '#f9f6f2',
              borderRadius: 10,
              boxShadow: '0 1px 4px #e2cfa1',
              padding: 24,
              minWidth: 220,
              maxWidth: 260,
              flex: '1 1 220px',
              textAlign: 'center',
              transition: 'transform 0.1s',
              fontWeight: 600
            }}
            onMouseOver={e => e.currentTarget.style.transform = 'scale(1.03)'}
            onMouseOut={e => e.currentTarget.style.transform = 'scale(1)'}
          >
            <div style={{ fontSize: 36, marginBottom: 12 }}>{feature.icon}</div>
            <div style={{ fontSize: 20, marginBottom: 8 }}>{feature.title}</div>
            <div style={{ fontWeight: 400, fontSize: 15 }}>{feature.description}</div>
          </Link>
        ))}
      </div>

      {/* About Section */}
      <div style={{
        background: '#E3F0FF',
        color: '#2C3E50',
        borderRadius: 10,
        padding: 20,
        marginBottom: 24,
        boxShadow: '0 1px 4px #b7d7b0',
        fontSize: 16
      }}>
        <strong>About this Community:</strong> <br />
        We are a group of believers dedicated to supporting each other in our walk with Christ. Whether you're new to faith or have been a Christian for years, you're welcome here!
      </div>

      {/* Call to Action */}
      <div style={{
        background: '#B7D7B0',
        color: '#2C3E50',
        borderRadius: 10,
        padding: 18,
        textAlign: 'center',
        fontWeight: 600,
        fontSize: 18
      }}>
        <span>Share your testimony or join a group today and be a blessing to others!</span>
      </div>
    </div>
  );
}

function LifeGroups() {
  const lifeGroups = [
    { name: 'Downtown Fellowship', time: 'Wednesdays 7pm', location: '123 Main St' },
    { name: 'Young Adults Group', time: 'Fridays 6pm', location: '456 Oak Ave' },
    { name: 'Morning Prayer Circle', time: 'Sundays 8am', location: '789 Pine Rd' },
  ];
  return (
    <section>
      <h2>Life Groups Near You</h2>
      <ul>
        {lifeGroups.map((group, idx) => (
          <li key={idx} style={{ marginBottom: 8, background: '#fffbe6', padding: 12, borderRadius: 8, boxShadow: '0 1px 4px #e2cfa1' }}>
            <strong>{group.name}</strong> <br/>
            <span>{group.time} | {group.location}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function BibleDiscussions() {
  const bibleBooks = [
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy",
    "Joshua", "Judges", "Ruth", "1 Samuel", "2 Samuel",
    "1 Kings", "2 Kings", "1 Chronicles", "2 Chronicles", "Ezra",
    "Nehemiah", "Esther", "Job", "Psalms", "Proverbs",
    "Ecclesiastes", "Song of Solomon", "Isaiah", "Jeremiah", "Lamentations",
    "Ezekiel", "Daniel", "Hosea", "Joel", "Amos",
    "Obadiah", "Jonah", "Micah", "Nahum", "Habakkuk",
    "Zephaniah", "Haggai", "Zechariah", "Malachi",
    "Matthew", "Mark", "Luke", "John", "Acts",
    "Romans", "1 Corinthians", "2 Corinthians", "Galatians", "Ephesians",
    "Philippians", "Colossians", "1 Thessalonians", "2 Thessalonians", "1 Timothy",
    "2 Timothy", "Titus", "Philemon", "Hebrews", "James",
    "1 Peter", "2 Peter", "1 John", "2 John", "3 John",
    "Jude", "Revelation"
  ];

  const allDiscussions = {
    "Matthew": [
      { user: 'Sarah', comment: 'The Great Commission inspires me to share my faith.' },
      { user: 'John', comment: 'I love how Jesus promises to be with us always.' },
      { user: 'Maria', comment: 'Verse 19 reminds us to make disciples of all nations.' },
    ],
    "John": [
      { user: 'Alex', comment: 'John 3:16 is the heart of the gospel.' },
      { user: 'Beth', comment: 'Nicodemus\'s story is so relatable.' },
    ],
    "Romans": [
      { user: 'Chris', comment: 'Nothing can separate us from God\'s love!' },
      { user: 'Dana', comment: 'Romans 8:28 gives me hope every day.' },
    ],
  };

  const [selectedBook, setSelectedBook] = React.useState("Matthew");

  return (
    <section>
      <h2>Bible Discussions</h2>
      <div style={{ marginBottom: 16 }}>
        <label htmlFor="book-select" style={{ marginRight: 8, fontWeight: 600, color: '#8B5C2A' }}>Select a Book:</label>
        <select
          id="book-select"
          value={selectedBook}
          onChange={e => setSelectedBook(e.target.value)}
          style={{
            padding: 10,
            borderRadius: 8,
            border: '2px solid #8B5C2A',
            color: '#8B5C2A',
            background: '#fff7d6',
            fontWeight: 700,
            fontSize: 16,
            outline: 'none',
            boxShadow: '0 1px 4px #e2cfa1'
          }}
        >
          {bibleBooks.map(book => (
            <option key={book} value={book} style={{ color: '#8B5C2A', background: '#fffbe6' }}>
              {book}
            </option>
          ))}
        </select>
      </div>
      <ul>
        {(allDiscussions[selectedBook] || [
          { user: 'No discussions yet', comment: 'Be the first to share your thoughts on this book!' }
        ]).map((d, idx) => (
          <li key={idx} style={{ marginBottom: 8, background: '#f9f6f2', padding: 12, borderRadius: 8, borderLeft: '4px solid #8B5C2A' }}>
            <strong>{d.user}:</strong> {d.comment}
          </li>
        ))}
      </ul>
    </section>
  );
}

function BibleVersions() {
  const [selectedBook, setSelectedBook] = React.useState("John");
  const [selectedChapter, setSelectedChapter] = React.useState(3);
  const [selectedVerse, setSelectedVerse] = React.useState(16);
  const [selectedVersion, setSelectedVersion] = React.useState("KJV");
  const [bibleText, setBibleText] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState("");

  // Available Bible versions
  const bibleVersions = [
    { code: "KJV", name: "King James Version" },
    { code: "NIV", name: "New International Version" },
    { code: "ESV", name: "English Standard Version" },
    { code: "NLT", name: "New Living Translation" },
    { code: "NKJV", name: "New King James Version" },
    { code: "CSB", name: "Christian Standard Bible" },
    { code: "NASB", name: "New American Standard Bible" },
    { code: "RSV", name: "Revised Standard Version" },
    { code: "ASV", name: "American Standard Version" },
    { code: "DRB", name: "Douay-Rheims Bible" },
    { code: "CEV", name: "Contemporary English Version" },
    { code: "GNT", name: "Good News Translation" },
    { code: "MSG", name: "The Message" },
    { code: "AMP", name: "Amplified Bible" },
    { code: "CEB", name: "Common English Bible" },
    { code: "HCSB", name: "Holman Christian Standard Bible" },
    { code: "PHILLIPS", name: "J.B. Phillips New Testament" },
    { code: "WEB", name: "World English Bible" },
    { code: "YLT", name: "Young's Literal Translation" },
    { code: "WYC", name: "Wycliffe Bible" }
  ];

  // Bible books with their chapter and verse counts
  const bibleBooks = [
    { name: "Genesis", chapters: 50, verses: [31,25,24,26,32,22,24,22,29,32,32,20,18,24,21,16,27,33,38,18,34,24,20,67,34,35,46,22,35,43,55,32,20,31,29,43,36,30,23,23,57,38,34,34,28,34,31,22,33,26] },
    { name: "Exodus", chapters: 40, verses: [22,25,22,31,23,30,25,32,35,29,10,51,22,31,27,36,16,27,25,26,36,31,33,18,40,37,21,43,46,38,18,35,23,35,35,38,29,31,43,38] },
    { name: "Leviticus", chapters: 27, verses: [17,16,17,35,19,30,38,36,24,20,47,8,59,57,33,34,16,30,37,27,24,33,44,23,55,46,34] },
    { name: "Numbers", chapters: 36, verses: [54,34,51,49,31,27,89,26,23,36,35,16,33,45,41,50,13,32,22,29,35,41,30,25,18,65,23,31,40,16,54,42,56,29,34,13] },
    { name: "Deuteronomy", chapters: 34, verses: [46,37,29,49,33,25,26,20,29,22,32,32,18,29,23,22,20,22,21,20,23,30,25,22,19,19,26,68,29,20,30,52,29,12] },
    { name: "Joshua", chapters: 24, verses: [18,24,17,24,15,27,26,35,27,43,23,24,33,15,63,10,18,28,51,9,45,34,16,33] },
    { name: "Judges", chapters: 21, verses: [36,23,31,24,31,40,25,35,57,18,40,15,25,20,20,31,13,31,30,48,25] },
    { name: "Ruth", chapters: 4, verses: [22,23,18,22] },
    { name: "1 Samuel", chapters: 31, verses: [28,36,21,22,12,21,17,22,27,27,15,25,23,52,35,23,58,30,24,42,15,23,29,22,44,25,12,25,11,31,13] },
    { name: "2 Samuel", chapters: 24, verses: [27,32,39,12,25,23,29,18,13,19,27,31,39,33,37,23,29,33,43,26,22,51,39,25] },
    { name: "1 Kings", chapters: 22, verses: [53,46,28,34,18,38,51,66,28,29,43,33,34,31,34,34,24,46,21,43,29,53] },
    { name: "2 Kings", chapters: 25, verses: [18,25,27,44,27,33,20,29,37,36,21,21,25,29,38,20,41,37,37,21,26,20,37,20,30] },
    { name: "1 Chronicles", chapters: 29, verses: [54,55,24,43,26,81,40,40,44,14,47,40,14,17,29,43,27,17,19,8,30,19,32,31,31,32,34,21,30] },
    { name: "2 Chronicles", chapters: 36, verses: [17,18,17,22,14,42,22,18,31,19,23,16,22,15,19,14,19,34,11,37,20,12,21,27,28,23,9,27,36,27,21,33,25,33,27,23] },
    { name: "Ezra", chapters: 10, verses: [11,70,13,24,17,22,28,36,15,44] },
    { name: "Nehemiah", chapters: 13, verses: [11,20,32,23,19,19,73,18,38,39,36,47,31] },
    { name: "Esther", chapters: 10, verses: [22,23,15,17,14,14,10,17,32,3] },
    { name: "Job", chapters: 42, verses: [22,13,26,21,27,30,21,22,35,22,20,25,28,22,35,22,16,21,29,29,34,30,17,25,6,14,23,28,25,31,40,22,33,37,16,33,24,41,30,24,34,17] },
    { name: "Psalms", chapters: 150, verses: [6,12,8,8,12,10,17,9,20,18,7,8,6,7,5,11,15,50,14,9,13,31,6,10,22,12,14,9,11,12,24,11,22,22,28,12,40,22,13,17,13,11,5,26,17,11,9,14,20,23,19,9,6,7,23,13,11,11,17,12,8,12,11,10,13,20,7,35,36,5,24,20,28,23,10,12,20,72,13,19,16,8,18,12,13,17,7,18,52,17,16,15,5,23,11,13,12,9,9,5,8,28,22,35,45,48,43,13,31,7,10,10,9,8,18,19,2,29,176,7,8,9,4,8,5,6,5,6,8,8,3,18,3,3,21,26,9,8,24,13,10,7,12,15,21,10,20,14,9,6] },
    { name: "Proverbs", chapters: 31, verses: [33,22,35,27,23,35,27,36,18,32,31,28,25,35,33,33,28,24,29,30,31,29,35,34,28,28,27,28,27,33,31] },
    { name: "Ecclesiastes", chapters: 12, verses: [18,26,22,16,20,12,29,17,18,20,10,14] },
    { name: "Song of Solomon", chapters: 8, verses: [17,17,11,16,16,13,13,14] },
    { name: "Isaiah", chapters: 66, verses: [31,22,26,6,30,13,25,22,21,34,16,6,22,32,9,14,14,7,25,6,17,25,18,23,12,21,13,29,24,33,9,20,24,17,10,22,38,22,8,31,29,25,28,28,25,13,15,22,26,11,23,15,12,17,13,12,21,14,21,22,11,12,19,12,25,24] },
    { name: "Jeremiah", chapters: 52, verses: [19,37,25,31,31,30,34,22,26,25,23,17,27,22,21,21,27,23,15,18,14,30,40,10,38,24,22,17,32,24,40,44,26,22,19,32,21,28,18,16,18,22,13,30,5,28,7,47,39,46,64,34] },
    { name: "Lamentations", chapters: 5, verses: [22,22,66,22,22] },
    { name: "Ezekiel", chapters: 48, verses: [28,10,27,17,17,14,27,18,11,22,25,28,23,23,8,63,24,32,14,49,32,31,49,27,17,21,36,26,21,26,18,32,33,31,15,38,28,23,29,49,26,20,27,31,25,24,23,35] },
    { name: "Daniel", chapters: 12, verses: [21,49,30,37,31,28,28,27,27,21,45,13] },
    { name: "Hosea", chapters: 14, verses: [11,23,5,19,15,11,16,14,17,15,12,14,16,9] },
    { name: "Joel", chapters: 3, verses: [20,32,21] },
    { name: "Amos", chapters: 9, verses: [15,16,15,13,27,14,17,14,15] },
    { name: "Obadiah", chapters: 1, verses: [21] },
    { name: "Jonah", chapters: 4, verses: [17,10,10,11] },
    { name: "Micah", chapters: 7, verses: [16,13,12,13,15,16,20] },
    { name: "Nahum", chapters: 3, verses: [15,13,19] },
    { name: "Habakkuk", chapters: 3, verses: [17,20,19] },
    { name: "Zephaniah", chapters: 3, verses: [18,15,20] },
    { name: "Haggai", chapters: 2, verses: [15,23] },
    { name: "Zechariah", chapters: 14, verses: [21,13,10,14,11,15,14,23,17,12,17,14,9,21] },
    { name: "Malachi", chapters: 4, verses: [14,17,18,6] },
    { name: "Matthew", chapters: 28, verses: [25,23,17,25,48,34,29,34,38,42,30,50,58,36,39,28,27,35,30,34,46,46,39,51,46,75,66,20] },
    { name: "Mark", chapters: 16, verses: [45,28,35,41,43,56,37,38,50,52,33,44,37,72,47,20] },
    { name: "Luke", chapters: 24, verses: [80,52,38,44,39,49,50,56,62,42,54,59,35,35,32,31,37,43,48,47,38,71,56,53] },
    { name: "John", chapters: 21, verses: [51,25,36,54,47,71,53,59,41,42,57,50,38,31,27,33,26,40,42,31,25] },
    { name: "Acts", chapters: 28, verses: [26,47,26,37,42,15,60,40,43,48,30,25,52,28,41,40,34,28,41,38,40,30,35,27,27,32,44,31] },
    { name: "Romans", chapters: 16, verses: [32,29,31,25,21,23,25,39,33,21,36,21,14,23,33,27] },
    { name: "1 Corinthians", chapters: 16, verses: [31,16,23,21,13,20,40,13,27,33,34,31,13,40,58,24] },
    { name: "2 Corinthians", chapters: 13, verses: [24,17,18,18,21,18,16,24,15,18,33,21,14] },
    { name: "Galatians", chapters: 6, verses: [24,21,29,31,26,18] },
    { name: "Ephesians", chapters: 6, verses: [23,22,21,32,33,24] },
    { name: "Philippians", chapters: 4, verses: [30,30,21,23] },
    { name: "Colossians", chapters: 4, verses: [29,23,25,18] },
    { name: "1 Thessalonians", chapters: 5, verses: [10,20,13,18,28] },
    { name: "2 Thessalonians", chapters: 3, verses: [12,17,18] },
    { name: "1 Timothy", chapters: 6, verses: [20,15,16,16,25,21] },
    { name: "2 Timothy", chapters: 4, verses: [18,26,17,22] },
    { name: "Titus", chapters: 3, verses: [16,15,15] },
    { name: "Philemon", chapters: 1, verses: [25] },
    { name: "Hebrews", chapters: 13, verses: [14,18,19,16,14,20,28,13,28,39,40,29,25] },
    { name: "James", chapters: 5, verses: [27,26,18,17,20] },
    { name: "1 Peter", chapters: 5, verses: [25,25,22,19,14] },
    { name: "2 Peter", chapters: 3, verses: [21,22,18] },
    { name: "1 John", chapters: 5, verses: [10,29,24,21,21] },
    { name: "2 John", chapters: 1, verses: [13] },
    { name: "3 John", chapters: 1, verses: [14] },
    { name: "Jude", chapters: 1, verses: [25] },
    { name: "Revelation", chapters: 22, verses: [20,29,22,11,14,17,17,13,21,11,19,17,18,20,8,21,18,24,21,15,27,21] }
  ];

  // Function to fetch Bible text
  const fetchBibleText = async () => {
    setLoading(true);
    setError("");
    
    try {
      const response = await fetch(`https://bible-api.com/${selectedBook.toLowerCase()}+${selectedChapter}:${selectedVerse}`);
      const data = await response.json();
      
      if (data.error) {
        setError("Verse not found. Please check your selection.");
        setBibleText("");
      } else {
        setBibleText(data.text);
      }
    } catch (err) {
      setError("Failed to load Bible text. Please try again.");
      setBibleText("");
    } finally {
      setLoading(false);
    }
  };

  // Fetch text when selection changes
  React.useEffect(() => {
    fetchBibleText();
  }, [selectedBook, selectedChapter, selectedVerse]);

  // Get current book's data
  const currentBook = bibleBooks.find(book => book.name === selectedBook);
  const maxChapters = currentBook ? currentBook.chapters : 1;
  const maxVerses = currentBook && currentBook.verses[selectedChapter - 1] ? currentBook.verses[selectedChapter - 1] : 1;

  return (
    <section>
      <h2>Bible Reader</h2>
      
      {/* Selection Controls */}
      <div style={{ marginBottom: 24, background: '#fffbe6', padding: 16, borderRadius: 8, boxShadow: '0 1px 4px #e2cfa1' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, marginBottom: 16 }}>
          {/* Book Selector */}
          <div>
            <label style={{ fontWeight: 600, color: '#8B5C2A', marginRight: 8 }}>Book:</label>
            <select
              value={selectedBook}
              onChange={e => {
                setSelectedBook(e.target.value);
                setSelectedChapter(1);
                setSelectedVerse(1);
              }}
              style={{
                padding: 8,
                borderRadius: 6,
                border: '2px solid #8B5C2A',
                color: '#8B5C2A',
                background: '#fff7d6',
                fontWeight: 600
              }}
            >
              {bibleBooks.map(book => (
                <option key={book.name} value={book.name}>{book.name}</option>
              ))}
            </select>
          </div>

          {/* Chapter Selector */}
          <div>
            <label style={{ fontWeight: 600, color: '#8B5C2A', marginRight: 8 }}>Chapter:</label>
            <select
              value={selectedChapter}
              onChange={e => {
                setSelectedChapter(parseInt(e.target.value));
                setSelectedVerse(1);
              }}
              style={{
                padding: 8,
                borderRadius: 6,
                border: '2px solid #8B5C2A',
                color: '#8B5C2A',
                background: '#fff7d6',
                fontWeight: 600
              }}
            >
              {Array.from({ length: maxChapters }, (_, i) => i + 1).map(chapter => (
                <option key={chapter} value={chapter}>{chapter}</option>
              ))}
            </select>
          </div>

          {/* Verse Selector */}
          <div>
            <label style={{ fontWeight: 600, color: '#8B5C2A', marginRight: 8 }}>Verse:</label>
            <select
              value={selectedVerse}
              onChange={e => setSelectedVerse(parseInt(e.target.value))}
              style={{
                padding: 8,
                borderRadius: 6,
                border: '2px solid #8B5C2A',
                color: '#8B5C2A',
                background: '#fff7d6',
                fontWeight: 600
              }}
            >
              {Array.from({ length: maxVerses }, (_, i) => i + 1).map(verse => (
                <option key={verse} value={verse}>{verse}</option>
              ))}
            </select>
          </div>

          {/* Version Selector */}
          <div>
            <label style={{ fontWeight: 600, color: '#8B5C2A', marginRight: 8 }}>Version:</label>
            <select
              value={selectedVersion}
              onChange={e => setSelectedVersion(e.target.value)}
              style={{
                padding: 8,
                borderRadius: 6,
                border: '2px solid #8B5C2A',
                color: '#8B5C2A',
                background: '#fff7d6',
                fontWeight: 600
              }}
            >
              {bibleVersions.map(version => (
                <option key={version.code} value={version.code}>{version.name}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Reference Display */}
        <div style={{ fontWeight: 700, color: '#8B5C2A', fontSize: 18 }}>
          {selectedBook} {selectedChapter}:{selectedVerse} ({selectedVersion})
        </div>
      </div>

      {/* Bible Text Display */}
      <div style={{ background: '#f9f6f2', padding: 20, borderRadius: 8, borderLeft: '4px solid #8B5C2A' }}>
        {loading && (
          <div style={{ textAlign: 'center', color: '#8B5C2A', fontStyle: 'italic' }}>
            Loading Bible text...
          </div>
        )}
        
        {error && (
          <div style={{ color: '#d32f2f', fontWeight: 600, marginBottom: 16 }}>
            {error}
          </div>
        )}
        
        {bibleText && !loading && (
          <div style={{ fontSize: 18, lineHeight: 1.6, color: '#2c3e50' }}>
            {bibleText}
          </div>
        )}
      </div>

      {/* Note about versions */}
      <div style={{ marginTop: 16, padding: 12, background: '#E3F0FF', borderRadius: 6, fontSize: 14, color: '#2C3E50' }}>
        <strong>Note:</strong> Currently displaying World English Bible. Multiple version support coming soon!
      </div>
    </section>
  );
}

function Testimonies() {
  const [testimonies, setTestimonies] = React.useState([]);
  const [name, setName] = React.useState("");
  const [story, setStory] = React.useState("");
  const [shareName, setShareName] = React.useState(false);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!story.trim()) return;
    setTestimonies([
      { name: shareName && name.trim() ? name : "Anonymous", story },
      ...testimonies,
    ]);
    setName("");
    setStory("");
    setShareName(false);
  };

  return (
    <section>
      <h2>Testimonies</h2>
      <form onSubmit={handleSubmit} style={{ marginBottom: 24, background: '#fffbe6', padding: 16, borderRadius: 8, boxShadow: '0 1px 4px #e2cfa1' }}>
        <div style={{ marginBottom: 12 }}>
          <label style={{ fontWeight: 600, color: '#8B5C2A' }}>
            Name (optional):
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              style={{ marginLeft: 8, padding: 6, borderRadius: 6, border: '1px solid #8B5C2A', background: '#fff7d6', color: '#8B5C2A' }}
              disabled={!shareName}
              placeholder="Leave blank for anonymous"
            />
          </label>
        </div>
        <div style={{ marginBottom: 12 }}>
          <label style={{ fontWeight: 600, color: '#8B5C2A' }}>
            <input
              type="checkbox"
              checked={shareName}
              onChange={e => setShareName(e.target.checked)}
              style={{ marginRight: 8 }}
            />
            Share my name with my testimony
          </label>
        </div>
        <div style={{ marginBottom: 12 }}>
          <label style={{ fontWeight: 600, color: '#8B5C2A' }}>
            Your Testimony:
            <textarea
              value={story}
              onChange={e => setStory(e.target.value)}
              required
              rows={4}
              style={{ display: 'block', width: '100%', marginTop: 8, padding: 8, borderRadius: 6, border: '1px solid #8B5C2A', background: '#fff7d6', color: '#8B5C2A' }}
              placeholder="Share your story of what brought you to Jesus..."
            />
          </label>
        </div>
        <button type="submit" style={{ background: '#8B5C2A', color: '#fff', padding: '8px 20px', border: 'none', borderRadius: 6, fontWeight: 700, cursor: 'pointer' }}>
          Submit Testimony
        </button>
      </form>
      <ul style={{ listStyle: 'none', padding: 0 }}>
        {testimonies.length === 0 && <li style={{ color: '#8B5C2A', fontStyle: 'italic' }}>No testimonies yet. Be the first to share your story!</li>}
        {testimonies.map((t, idx) => (
          <li key={idx} style={{ marginBottom: 16, background: '#f9f6f2', padding: 16, borderRadius: 8, borderLeft: '4px solid #8B5C2A' }}>
            <strong>{t.name}</strong> <br/>
            <span>{t.story}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function PrayerWall() {
  const [requests, setRequests] = React.useState([]);
  const [firstName, setFirstName] = React.useState("");
  const [request, setRequest] = React.useState("");
  const [commentInputs, setCommentInputs] = React.useState({});

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!firstName.trim() || !request.trim()) return;
    setRequests([
      { firstName: firstName.trim(), request: request.trim(), comments: [] },
      ...requests,
    ]);
    setFirstName("");
    setRequest("");
  };

  const handleCommentChange = (idx, value) => {
    setCommentInputs({ ...commentInputs, [idx]: value });
  };

  const handleAddComment = (idx) => {
    const comment = commentInputs[idx]?.trim();
    if (!comment) return;
    setRequests(requests =>
      requests.map((req, i) =>
        i === idx ? { ...req, comments: [...req.comments, comment] } : req
      )
    );
    setCommentInputs({ ...commentInputs, [idx]: "" });
  };

  return (
    <section>
      <h2>Prayer Wall</h2>
      <form onSubmit={handleSubmit} style={{ marginBottom: 24, background: '#fffbe6', padding: 16, borderRadius: 8, boxShadow: '0 1px 4px #e2cfa1' }}>
        <div style={{ marginBottom: 12 }}>
          <label style={{ fontWeight: 600, color: '#8B5C2A' }}>
            First Name:
            <input
              type="text"
              value={firstName}
              onChange={e => setFirstName(e.target.value)}
              required
              style={{ marginLeft: 8, padding: 6, borderRadius: 6, border: '1px solid #8B5C2A', background: '#fff7d6', color: '#8B5C2A' }}
              placeholder="Enter your first name"
            />
          </label>
        </div>
        <div style={{ marginBottom: 12 }}>
          <label style={{ fontWeight: 600, color: '#8B5C2A' }}>
            Prayer Request / Trial:
            <textarea
              value={request}
              onChange={e => setRequest(e.target.value)}
              required
              rows={3}
              style={{ display: 'block', width: '100%', marginTop: 8, padding: 8, borderRadius: 6, border: '1px solid #8B5C2A', background: '#fff7d6', color: '#8B5C2A' }}
              placeholder="How can we pray for you?"
            />
          </label>
        </div>
        <button type="submit" style={{ background: '#8B5C2A', color: '#fff', padding: '8px 20px', border: 'none', borderRadius: 6, fontWeight: 700, cursor: 'pointer' }}>
          Post to Prayer Wall
        </button>
      </form>
      <ul style={{ listStyle: 'none', padding: 0 }}>
        {requests.length === 0 && <li style={{ color: '#8B5C2A', fontStyle: 'italic' }}>No prayer requests yet. Be the first to share!</li>}
        {requests.map((req, idx) => (
          <li key={idx} style={{ marginBottom: 24, background: '#f9f6f2', padding: 16, borderRadius: 8, borderLeft: '4px solid #8B5C2A' }}>
            <strong>{req.firstName}</strong> <br/>
            <span>{req.request}</span>
            <div style={{ marginTop: 12 }}>
              <strong>Comments & Encouragement:</strong>
              <ul style={{ listStyle: 'none', padding: 0, marginTop: 8 }}>
                {req.comments.length === 0 && <li style={{ color: '#8B5C2A', fontStyle: 'italic' }}>No comments yet.</li>}
                {req.comments.map((c, cidx) => (
                  <li key={cidx} style={{ marginBottom: 6, background: '#fffbe6', padding: 8, borderRadius: 6 }}>{c}</li>
                ))}
              </ul>
              <div style={{ marginTop: 8 }}>
                <input
                  type="text"
                  value={commentInputs[idx] || ""}
                  onChange={e => handleCommentChange(idx, e.target.value)}
                  placeholder="Add encouragement or prayer..."
                  style={{ 
                    width: '70%', 
                    padding: 6, 
                    borderRadius: 6, 
                    border: '1px solid #8B5C2A', 
                    background: '#fff7d6', 
                    color: '#8B5C2A',
                    marginRight: 8
                  }}
                />
                <button
                  type="button"
                  onClick={() => handleAddComment(idx)}
                  style={{ 
                    background: '#8B5C2A', 
                    color: '#fff', 
                    padding: '6px 12px', 
                    border: 'none', 
                    borderRadius: 6, 
                    fontWeight: 600, 
                    cursor: 'pointer' 
                  }}
                >
                  Add Comment
                </button>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function MusicForum() {
  const [songs, setSongs] = React.useState([]);
  const [title, setTitle] = React.useState("");
  const [artist, setArtist] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [category, setCategory] = React.useState("Worship");

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!title.trim() || !artist.trim()) return;
    setSongs([
      { title: title.trim(), artist: artist.trim(), description: description.trim(), category },
      ...songs,
    ]);
    setTitle("");
    setArtist("");
    setDescription("");
    setCategory("Worship");
  };

  const categories = ["Worship", "Praise", "Gospel", "Contemporary", "Hymns", "Instrumental"];

  return (
    <section>
      <h2>Christian Music Forum</h2>
      <form onSubmit={handleSubmit} style={{ marginBottom: 24, background: '#fffbe6', padding: 16, borderRadius: 8, boxShadow: '0 1px 4px #e2cfa1' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: 12 }}>
          <div>
            <label style={{ fontWeight: 600, color: '#8B5C2A' }}>
              Song Title:
              <input
                type="text"
                value={title}
                onChange={e => setTitle(e.target.value)}
                required
                style={{ marginLeft: 8, padding: 6, borderRadius: 6, border: '1px solid #8B5C2A', background: '#fff7d6', color: '#8B5C2A' }}
                placeholder="Enter song title"
              />
            </label>
          </div>
          <div>
            <label style={{ fontWeight: 600, color: '#8B5C2A' }}>
              Artist:
              <input
                type="text"
                value={artist}
                onChange={e => setArtist(e.target.value)}
                required
                style={{ marginLeft: 8, padding: 6, borderRadius: 6, border: '1px solid #8B5C2A', background: '#fff7d6', color: '#8B5C2A' }}
                placeholder="Enter artist name"
              />
            </label>
          </div>
          <div>
            <label style={{ fontWeight: 600, color: '#8B5C2A' }}>
              Category:
              <select
                value={category}
                onChange={e => setCategory(e.target.value)}
                style={{ marginLeft: 8, padding: 6, borderRadius: 6, border: '1px solid #8B5C2A', background: '#fff7d6', color: '#8B5C2A' }}
              >
                {categories.map(cat => (
                  <option key={cat} value={cat}>{cat}</option>
                ))}
              </select>
            </label>
          </div>
        </div>
        <div style={{ marginBottom: 12 }}>
          <label style={{ fontWeight: 600, color: '#8B5C2A' }}>
            Description (optional):
            <textarea
              value={description}
              onChange={e => setDescription(e.target.value)}
              rows={3}
              style={{ display: 'block', width: '100%', marginTop: 8, padding: 8, borderRadius: 6, border: '1px solid #8B5C2A', background: '#fff7d6', color: '#8B5C2A' }}
              placeholder="Share why this song is meaningful to you..."
            />
          </label>
        </div>
        <button type="submit" style={{ background: '#8B5C2A', color: '#fff', padding: '8px 20px', border: 'none', borderRadius: 6, fontWeight: 700, cursor: 'pointer' }}>
          Share Song
        </button>
      </form>
      
      <div style={{ marginBottom: 16 }}>
        <h3>Shared Songs</h3>
        {songs.length === 0 && <p style={{ color: '#8B5C2A', fontStyle: 'italic' }}>No songs shared yet. Be the first to share your favorite Christian music!</p>}
      </div>
      
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {songs.map((song, idx) => (
          <div key={idx} style={{ background: '#f9f6f2', padding: 16, borderRadius: 8, borderLeft: '4px solid #8B5C2A' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
              <div>
                <strong style={{ fontSize: 18 }}>{song.title}</strong>
                <div style={{ color: '#666', fontSize: 14 }}>by {song.artist}</div>
              </div>
              <span style={{ 
                background: '#8B5C2A', 
                color: '#fff', 
                padding: '4px 8px', 
                borderRadius: 4, 
                fontSize: 12, 
                fontWeight: 600 
              }}>
                {song.category}
              </span>
            </div>
            {song.description && (
              <div style={{ marginTop: 8, fontStyle: 'italic', color: '#555' }}>
                "{song.description}"
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

function App() {
  return (
    <Router>
      <div style={{ 
        minHeight: '100vh', 
        background: 'linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)',
        fontFamily: 'Arial, sans-serif'
      }}>
        {/* Header */}
        <header style={{
          background: '#8B5C2A',
          color: '#fff',
          padding: '16px 24px',
          boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
          position: 'sticky',
          top: 0,
          zIndex: 100
        }}>
          <div style={{ 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'space-between',
            maxWidth: 1200,
            margin: '0 auto'
          }}>
            <Link to="/" style={{ 
              display: 'flex', 
              alignItems: 'center', 
              textDecoration: 'none', 
              color: '#fff',
              fontWeight: 700,
              fontSize: 24
            }}>
              <BrownCross />
              <span style={{ marginLeft: 12 }}>Christian Community</span>
            </Link>
            
            <nav style={{ display: 'flex', gap: 24 }}>
              <Link to="/" style={{ color: '#fff', textDecoration: 'none', fontWeight: 600 }}>Home</Link>
              <Link to="/life-groups" style={{ color: '#fff', textDecoration: 'none', fontWeight: 600 }}>Life Groups</Link>
              <Link to="/bible-discussions" style={{ color: '#fff', textDecoration: 'none', fontWeight: 600 }}>Bible</Link>
              <Link to="/bible-versions" style={{ color: '#fff', textDecoration: 'none', fontWeight: 600 }}>Bible Reader</Link>
              <Link to="/testimonies" style={{ color: '#fff', textDecoration: 'none', fontWeight: 600 }}>Testimonies</Link>
              <Link to="/prayer-wall" style={{ color: '#fff', textDecoration: 'none', fontWeight: 600 }}>Prayer</Link>
              <Link to="/music-forum" style={{ color: '#fff', textDecoration: 'none', fontWeight: 600 }}>Music</Link>
            </nav>
          </div>
        </header>

        {/* Main Content */}
        <main style={{ 
          maxWidth: 1200, 
          margin: '0 auto', 
          padding: '24px',
          minHeight: 'calc(100vh - 80px)'
        }}>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/life-groups" element={<LifeGroups />} />
            <Route path="/bible-discussions" element={<BibleDiscussions />} />
            <Route path="/bible-versions" element={<BibleVersions />} />
            <Route path="/testimonies" element={<Testimonies />} />
            <Route path="/prayer-wall" element={<PrayerWall />} />
            <Route path="/music-forum" element={<MusicForum />} />
          </Routes>
        </main>

        {/* Footer */}
        <footer style={{
          background: '#2C3E50',
          color: '#fff',
          textAlign: 'center',
          padding: '20px',
          marginTop: 'auto'
        }}>
          <p style={{ margin: 0, fontSize: 14 }}>
            © 2024 Christian Community Dashboard. Built with love for the body of Christ.
          </p>
        </footer>
      </div>
    </Router>
  );
}

export default App;