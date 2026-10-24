import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

const client = axios.create({
  baseURL: API_BASE_URL,
  timeout: 25000,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
});

// Request interceptor to attach Bearer token if present
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('stocksense_token');
  if (token && !config.headers['Authorization']) {
    config.headers['Authorization'] = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor for clear error handling
client.interceptors.response.use(
  (response) => response,
  (error) => {
    let message = 'An unexpected error occurred.';
    if (error.response?.data?.detail) {
      if (typeof error.response.data.detail === 'string') {
        message = error.response.data.detail;
      } else if (Array.isArray(error.response.data.detail)) {
        message = error.response.data.detail.map((d) => d.msg || JSON.stringify(d)).join(', ');
      }
    } else if (error.message) {
      message = error.message;
    }
    error.userMessage = message;
    return Promise.reject(error);
  }
);

export const api = {
  client,

  // --- Authentication ---
  login: (username, password) =>
    client.post('/api/auth/login', { username, password }).then((r) => {
      if (r.data?.access_token) {
        localStorage.setItem('stocksense_token', r.data.access_token);
        localStorage.setItem('stocksense_user', JSON.stringify(r.data.user));
      }
      return r.data;
    }),
  logout: () =>
    client.post('/api/auth/logout').finally(() => {
      localStorage.removeItem('stocksense_token');
      localStorage.removeItem('stocksense_user');
    }),
  getMe: () => client.get('/api/auth/me').then((r) => r.data),
  bootstrapAdmin: () => client.post('/api/auth/bootstrap-admin').then((r) => r.data),

  // System Health
  getHealth: () => client.get('/api/health').then((r) => r.data),
  resetDemoDatabase: () => client.post('/api/settings/reset-demo').then((r) => r.data),

  // Dashboard
  getDashboardSummary: (asOfDate) =>
    client.get('/api/dashboard/summary', { params: { as_of_date: asOfDate } }).then((r) => r.data),

  // Products
  getProducts: (params = {}) => client.get('/api/products', { params }).then((r) => r.data),
  getProduct: (id) => client.get(`/api/products/${id}`).then((r) => r.data),
  getProductByBarcode: (barcode) =>
    client.get(`/api/products/barcode/${encodeURIComponent(barcode)}`).then((r) => r.data),
  createProduct: (data) => client.post('/api/products', data).then((r) => r.data),
  updateProduct: (id, data) => client.patch(`/api/products/${id}`, data).then((r) => r.data),
  deleteProduct: (id) => client.delete(`/api/products/${id}`).then((r) => r.data),

  // Inventory & Stock Adjustments
  stockIn: (data) => client.post('/api/inventory/stock-in', data).then((r) => r.data),
  stockOut: (data) => client.post('/api/inventory/stock-out', data).then((r) => r.data),
  stockAdjustment: (data) => client.post('/api/inventory/adjustments', data).then((r) => r.data),
  getMovements: (params = {}) => client.get('/api/inventory/movements', { params }).then((r) => r.data),
  getLots: () => client.get('/api/inventory/lots').then((r) => r.data),

  // Sales
  getSales: (params = {}) => client.get('/api/sales', { params }).then((r) => r.data),
  recordSale: (data) => client.post('/api/sales', data).then((r) => r.data),

  // Demand Forecasts
  runForecast: (payload, asOfDate) =>
    client.post('/api/forecasts/run', payload, { params: { as_of_date: asOfDate } }).then((r) => r.data),
  getForecasts: (params = {}) => client.get('/api/forecasts', { params }).then((r) => r.data),

  // Forecast Accuracy (MAE & WAPE)
  getAccuracySummary: (asOfDate) =>
    client.get('/api/forecast-accuracy/summary', { params: { as_of_date: asOfDate } }).then((r) => r.data),
  getProductAccuracy: (asOfDate) =>
    client.get('/api/forecast-accuracy/products', { params: { as_of_date: asOfDate } }).then((r) => r.data),
  getAccuracyHistory: () => client.get('/api/forecast-accuracy/history').then((r) => r.data),
  runAccuracyBacktest: (payload, asOfDate) =>
    client.post('/api/forecast-accuracy/backtest', payload, { params: { as_of_date: asOfDate } }).then((r) => r.data),

  // Reorder Planner
  getReorderRecommendations: (zScore = 1.65, asOfDate) =>
    client.get('/api/reorder/recommendations', { params: { z_score: zScore, as_of_date: asOfDate } }).then((r) => r.data),

  // Purchase Orders
  getPurchaseOrders: (params = {}) => client.get('/api/purchase-orders', { params }).then((r) => r.data),
  createPurchaseOrder: (data) => client.post('/api/purchase-orders', data).then((r) => r.data),
  receivePurchaseOrder: (poId, data = {}) =>
    client.post(`/api/purchase-orders/${poId}/receive`, data).then((r) => r.data),

  // Smart Data Import
  previewImportText: (rawText, targetType = 'products') =>
    client.post('/api/imports/preview-text', { raw_text: rawText, target_type: targetType }).then((r) => r.data),
  previewImportFile: (formData) =>
    client
      .post('/api/imports/preview-file', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => r.data),
  commitImport: (data) => client.post('/api/imports/commit', data).then((r) => r.data),
  getImportHistory: () => client.get('/api/imports').then((r) => r.data),
  downloadImportTemplate: (format = 'csv') => {
    const url = `${API_BASE_URL}/api/imports/template.${format}`;
    const link = document.createElement('a');
    link.href = url;
    link.download = `StockSense_Products_Template.${format}`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  },

  // --- Rural Kirana Data Collection ---
  recordManualSale: (data) => client.post('/api/rural/manual-sale', data).then((r) => r.data),
  recordManualDelivery: (data) => client.post('/api/rural/manual-delivery', data).then((r) => r.data),
  parseVoice: (transcript) => client.post('/api/rural/voice-parse', { transcript }).then((r) => r.data),
  confirmVoice: (items, date) => client.post('/api/rural/voice-confirm', { items, date }).then((r) => r.data),
  parseNotebook: (rawText, source = 'PHOTO', filename) =>
    client.post('/api/rural/notebook-parse', { raw_text: rawText, source_type: source, filename }).then((r) => r.data),
  confirmNotebook: (rows, sessionId) =>
    client.post('/api/rural/notebook-confirm', { rows, session_id: sessionId }).then((r) => r.data),
  compareStockCount: (productId, countedStock) =>
    client.post('/api/rural/stock-count/compare', { product_id: productId, counted_stock: countedStock }).then((r) => r.data),
  commitStockCount: (productId, countedStock, reason) =>
    client.post('/api/rural/stock-count/commit', { product_id: productId, counted_stock: countedStock, reason }).then((r) => r.data),
  getDailyClosing: (asOfDate) =>
    client.get('/api/rural/daily-closing', { params: { as_of_date: asOfDate } }).then((r) => r.data),

  // --- Offline Synchronization ---
  syncOfflineBatch: (operations) => client.post('/api/sync/offline', { operations }).then((r) => r.data),
  getSyncQueue: () => client.get('/api/sync/queue').then((r) => r.data),

  // --- Admin User Management ---
  getAdminUsers: () => client.get('/api/admin/users').then((r) => r.data),
  createAdminUser: (data) => client.post('/api/admin/users', data).then((r) => r.data),
  toggleUserStatus: (userId, isActive) =>
    client.patch(`/api/admin/users/${userId}/status`, { is_active: isActive }).then((r) => r.data),
  changeUserRole: (userId, role) =>
    client.patch(`/api/admin/users/${userId}/role`, { role }).then((r) => r.data),
  resetUserPassword: (userId, newPassword) =>
    client.post(`/api/admin/users/${userId}/reset-password`, { new_password: newPassword }).then((r) => r.data),
  revokeUserSessions: (userId) => client.post(`/api/admin/users/${userId}/revoke-sessions`).then((r) => r.data),

  // --- Admin Audit & Security ---
  getAuditLogs: (params = {}) => client.get('/api/admin/audit/logs', { params }).then((r) => r.data),
  getAuditSummary: () => client.get('/api/admin/audit/summary').then((r) => r.data),

  // --- Admin Backup & Restore ---
  getBackupHealth: () => client.get('/api/admin/backup/health').then((r) => r.data),
  createBackup: (note) => client.post('/api/admin/backup/create', { note }).then((r) => r.data),
  listBackups: () => client.get('/api/admin/backup/list').then((r) => r.data),
  restoreBackup: (backupFilename, confirmText = 'CONFIRM_RESTORE') =>
    client.post('/api/admin/backup/restore', { backup_filename: backupFilename, confirm_text: confirmText }).then((r) => r.data),
  downloadBackupUrl: (filename) => `${API_BASE_URL}/api/admin/backup/download/${encodeURIComponent(filename)}`,

  // Download URLs
  getReportUrl: (type, asOfDate) => `${API_BASE_URL}/api/reports/${type}${asOfDate ? `?as_of_date=${asOfDate}` : ''}`,

  // --- Product Rate Modifications ---
  modifyProductRate: (productId, data) =>
    client.put(`/api/products/${productId}/rate`, data).then((r) => r.data),
  getProductRateHistory: (productId) =>
    client.get(`/api/products/${productId}/rate-history`).then((r) => r.data),
  getAllRecentRateHistory: (limit = 50) =>
    client.get('/api/products/rate-history/recent', { params: { limit } }).then((r) => r.data),

  // --- Customer & User Databases ---
  getDatabaseSummary: () => client.get('/api/database/summary').then((r) => r.data),
  getCustomers: () => client.get('/api/database/customers').then((r) => r.data),
  createCustomer: (data) => client.post('/api/database/customers', data).then((r) => r.data),
  getCustomerPurchases: (params = {}) => client.get('/api/database/customer-purchases', { params }).then((r) => r.data),
  recordCustomerBarcodePurchase: (data) => client.post('/api/database/customer-purchases', data).then((r) => r.data),
  getUserPurchases: (limit = 100) => client.get('/api/database/user-purchases', { params: { limit } }).then((r) => r.data),
  recordUserPurchase: (data) => client.post('/api/database/user-purchases', data).then((r) => r.data),
  downloadFullDatabaseExcel: async () => {
    const url = `${API_BASE_URL}/api/database/export-excel`;
    const token = localStorage.getItem('stocksense_token');
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    const response = await axios.get(url, { responseType: 'blob', headers });
    const blob = new Blob([response.data]);
    const link = document.createElement('a');
    link.href = window.URL.createObjectURL(blob);
    link.download = `StockSense_Full_Database_Report_${new Date().toISOString().slice(0, 10)}.xlsx`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(link.href);
  },
  analyzeExcelFile: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const token = localStorage.getItem('stocksense_token');
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    const res = await axios.post(`${API_BASE_URL}/api/database/analyze-excel`, formData, { headers });
    return res.data;
  },

  // Trigger file download helper
  downloadReport: async (type, filename, asOfDate) => {
    const url = `${API_BASE_URL}/api/reports/${type}${asOfDate ? `?as_of_date=${asOfDate}` : ''}`;
    const token = localStorage.getItem('stocksense_token');
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    const response = await axios.get(url, { responseType: 'blob', headers });
    const blob = new Blob([response.data]);
    const link = document.createElement('a');
    link.href = window.URL.createObjectURL(blob);
    link.download = filename || `StockSense_${type}`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(link.href);
  },
};

export default api;
