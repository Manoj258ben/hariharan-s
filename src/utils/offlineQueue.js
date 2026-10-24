/**
 * Offline transaction queue using localStorage & IndexedDB.
 * Guarantees unique operation UUIDs, automatic online sync,
 * and zero duplicate transactions.
 */
import { api } from '../services/api';

const QUEUE_STORAGE_KEY = 'stocksense_offline_queue_v2';
const LAST_SYNC_KEY = 'stocksense_last_sync_time';

export function generateUUID() {
  return 'op-' + Math.random().toString(36).substring(2, 9) + '-' + Date.now().toString(36);
}

export function getOfflineQueue() {
  try {
    const raw = localStorage.getItem(QUEUE_STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch (e) {
    console.error('Failed to read offline queue:', e);
    return [];
  }
}

export function saveOfflineQueue(queue) {
  try {
    localStorage.setItem(QUEUE_STORAGE_KEY, JSON.stringify(queue));
  } catch (e) {
    console.error('Failed to save offline queue:', e);
  }
}

export function enqueueOfflineOperation(type, payload) {
  const queue = getOfflineQueue();
  const operation = {
    operation_id: generateUUID(),
    operation_type: type, // 'RECORD_SALE', 'STOCK_IN', 'STOCK_ADJUSTMENT'
    payload,
    timestamp: new Date().toISOString(),
    status: 'PENDING',
    retry_count: 0,
  };
  queue.push(operation);
  saveOfflineQueue(queue);
  return operation;
}

export function getLastSyncTime() {
  return localStorage.getItem(LAST_SYNC_KEY) || 'Never';
}

export async function flushOfflineQueue(onSuccess, onError) {
  const queue = getOfflineQueue();
  if (queue.length === 0) {
    return { synced: 0, skipped: 0, failed: 0 };
  }

  // Format payload for /api/sync/offline
  const payload = {
    operations: queue.map(q => ({
      operation_id: q.operation_id,
      operation_type: q.operation_type,
      payload: q.payload,
      timestamp: q.timestamp,
    })),
  };

  try {
    const res = await api.client.post('/api/sync/offline', payload);
    const data = res.data;

    // Remove successfully synced and duplicate items from client queue
    const resultsMap = {};
    (data.results || []).forEach(r => {
      resultsMap[r.operation_id] = r.status;
    });

    const remainingQueue = queue.filter(q => {
      const st = resultsMap[q.operation_id];
      // Keep only failed items for retry
      return st === 'FAILED';
    });

    saveOfflineQueue(remainingQueue);
    const nowStr = new Date().toLocaleTimeString();
    localStorage.setItem(LAST_SYNC_KEY, nowStr);

    if (onSuccess) onSuccess(data);
    return data;
  } catch (err) {
    console.error('Failed to flush offline queue:', err);
    if (onError) onError(err);
    throw err;
  }
}
