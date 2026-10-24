import {
  INITIAL_CONFIG,
  INITIAL_SUPPLIERS,
  INITIAL_PRODUCTS,
  INITIAL_LOTS,
  INITIAL_DAILY_SALES,
  INITIAL_TRANSACTIONS
} from '../data/initialData';

const STORAGE_KEYS = {
  CONFIG: 'stocksense_config',
  PRODUCTS: 'stocksense_products',
  SUPPLIERS: 'stocksense_suppliers',
  LOTS: 'stocksense_lots',
  DAILY_SALES: 'stocksense_daily_sales',
  TRANSACTIONS: 'stocksense_transactions'
};

// Version bump this whenever breaking localStorage schema changes are made
const APP_VERSION = '2.0.1';
const VERSION_KEY = 'stocksense_version';

function bustCacheIfStale() {
  try {
    const stored = localStorage.getItem(VERSION_KEY);
    if (stored !== APP_VERSION) {
      console.info('[StockSense] Version changed (' + stored + ' -> ' + APP_VERSION + '). Clearing localStorage cache.');
      Object.values(STORAGE_KEYS).forEach(k => localStorage.removeItem(k));
      localStorage.setItem(VERSION_KEY, APP_VERSION);
    }
  } catch (e) {
    console.warn('[StockSense] Could not check version, skipping cache bust:', e);
  }
}

export const getStoredData = (key, fallback) => {
  try {
    const item = localStorage.getItem(key);
    if (!item) return fallback;
    const parsed = JSON.parse(item);
    // Sanity check: if type doesn't match fallback, return fallback
    if (Array.isArray(fallback) && !Array.isArray(parsed)) return fallback;
    if (typeof fallback === 'object' && fallback !== null && typeof parsed !== 'object') return fallback;
    return parsed;
  } catch (e) {
    console.warn('[StockSense] Corrupt data in ' + key + ', using defaults:', e);
    try { localStorage.removeItem(key); } catch (_) {}
    return fallback;
  }
};

export const setStoredData = (key, value) => {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch (e) {
    console.error('Error saving ' + key + ' to localStorage:', e);
  }
};

export const loadInitialAppState = () => {
  try {
    bustCacheIfStale();
  } catch (e) {
    console.warn('[StockSense] Cache bust failed:', e);
  }

  const config = getStoredData(STORAGE_KEYS.CONFIG, INITIAL_CONFIG);
  const products = getStoredData(STORAGE_KEYS.PRODUCTS, INITIAL_PRODUCTS);
  const suppliers = getStoredData(STORAGE_KEYS.SUPPLIERS, INITIAL_SUPPLIERS);
  const lots = getStoredData(STORAGE_KEYS.LOTS, INITIAL_LOTS);
  const dailySales = getStoredData(STORAGE_KEYS.DAILY_SALES, INITIAL_DAILY_SALES);
  const transactions = getStoredData(STORAGE_KEYS.TRANSACTIONS, INITIAL_TRANSACTIONS);

  return { config, products, suppliers, lots, dailySales, transactions };
};

export const resetToDemoData = () => {
  try {
    localStorage.setItem(STORAGE_KEYS.CONFIG, JSON.stringify(INITIAL_CONFIG));
    localStorage.setItem(STORAGE_KEYS.PRODUCTS, JSON.stringify(INITIAL_PRODUCTS));
    localStorage.setItem(STORAGE_KEYS.SUPPLIERS, JSON.stringify(INITIAL_SUPPLIERS));
    localStorage.setItem(STORAGE_KEYS.LOTS, JSON.stringify(INITIAL_LOTS));
    localStorage.setItem(STORAGE_KEYS.DAILY_SALES, JSON.stringify(INITIAL_DAILY_SALES));
    localStorage.setItem(STORAGE_KEYS.TRANSACTIONS, JSON.stringify(INITIAL_TRANSACTIONS));
  } catch (e) {
    console.error('Error resetting demo data:', e);
  }
  return {
    config: INITIAL_CONFIG,
    products: INITIAL_PRODUCTS,
    suppliers: INITIAL_SUPPLIERS,
    lots: INITIAL_LOTS,
    dailySales: INITIAL_DAILY_SALES,
    transactions: INITIAL_TRANSACTIONS
  };
};

export const saveAppState = ({ config, products, suppliers, lots, dailySales, transactions }) => {
  if (config) setStoredData(STORAGE_KEYS.CONFIG, config);
  if (products) setStoredData(STORAGE_KEYS.PRODUCTS, products);
  if (suppliers) setStoredData(STORAGE_KEYS.SUPPLIERS, suppliers);
  if (lots) setStoredData(STORAGE_KEYS.LOTS, lots);
  if (dailySales) setStoredData(STORAGE_KEYS.DAILY_SALES, dailySales);
  if (transactions) setStoredData(STORAGE_KEYS.TRANSACTIONS, transactions);
};

export const getStoredLanguage = () => {
  try {
    return localStorage.getItem('stocksense_language') || 'en';
  } catch {
    return 'en';
  }
};

export const setStoredLanguage = (lang) => {
  try {
    localStorage.setItem('stocksense_language', lang);
  } catch (e) {
    console.warn('Could not save language to storage:', e);
  }
};

export const getStorageStats = () => {
  try {
    let totalBytes = 0;
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      const v = localStorage.getItem(k);
      totalBytes += (k?.length || 0) + (v?.length || 0);
    }
    return {
      usedKB: (totalBytes / 1024).toFixed(1),
      itemCount: localStorage.length,
      quotaEstimateKB: 5120
    };
  } catch {
    return { usedKB: '0', itemCount: 0, quotaEstimateKB: 5120 };
  }
};

