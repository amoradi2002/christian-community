CREATE TABLE IF NOT EXISTS strategies (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT UNIQUE NOT NULL,
    type        TEXT NOT NULL,
    description TEXT,
    rules_json  TEXT NOT NULL,
    is_active   INTEGER DEFAULT 1,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS alerts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id  INTEGER REFERENCES strategies(id),
    symbol       TEXT NOT NULL,
    signal       TEXT NOT NULL,
    confidence   REAL,
    reasons      TEXT,
    price_at     REAL,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS performance (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id  INTEGER REFERENCES strategies(id),
    symbol       TEXT NOT NULL,
    signal       TEXT NOT NULL,
    entry_price  REAL NOT NULL,
    exit_price   REAL,
    outcome      TEXT,
    pnl_pct      REAL,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    closed_at    TIMESTAMP
);

CREATE TABLE IF NOT EXISTS model_snapshots (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    model_blob   BLOB NOT NULL,
    accuracy     REAL,
    features     TEXT,
    trained_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS market_cache (
    symbol       TEXT NOT NULL,
    timeframe    TEXT NOT NULL,
    date         TEXT NOT NULL,
    open_price   REAL,
    high_price   REAL,
    low_price    REAL,
    close_price  REAL,
    volume       INTEGER,
    PRIMARY KEY (symbol, timeframe, date)
);

CREATE TABLE IF NOT EXISTS trades (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id     TEXT,
    symbol       TEXT NOT NULL,
    side         TEXT NOT NULL,
    qty          REAL NOT NULL,
    order_type   TEXT,
    filled_price REAL,
    status       TEXT,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fundamentals_cache (
    symbol       TEXT PRIMARY KEY,
    data_json    TEXT,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS earnings_cache (
    symbol       TEXT NOT NULL,
    date         TEXT,
    data_json    TEXT,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);

CREATE TABLE IF NOT EXISTS flow_cache (
    flow_id      TEXT PRIMARY KEY,
    ticker       TEXT NOT NULL,
    data_json    TEXT,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS youtube_lessons (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    video_url    TEXT NOT NULL,
    video_id     TEXT UNIQUE NOT NULL,
    title        TEXT,
    channel_name TEXT,
    transcript   TEXT,
    extracted_strategies TEXT,
    status       TEXT DEFAULT 'pending',
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP
);
