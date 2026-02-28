/**
 * types.ts — TypeScript interfaces for the Braiins Pool API.
 */

export interface Worker {
  name: string;
  hashrate: string;
  status: 'active' | 'inactive' | 'offline';
  last_share: string;
}

export interface WorkerDetails extends Worker {
  shares_accepted: number;
  shares_rejected: number;
  temperature?: number;
  pool_url?: string;
}

export interface TimeSeries {
  timestamps: string[];
  values: number[];
  unit: string;
}

export interface EarningsSummary {
  unpaid_balance: string;
  currency: string;
  total_earned: string;
  last_payout?: string;
}

export interface Payout {
  id: string;
  amount: string;
  currency: string;
  timestamp: string;
  txid?: string;
  status: 'confirmed' | 'pending';
}

export interface PayoutEstimate {
  estimated_time: string;
  estimated_amount: string;
  currency: string;
  current_threshold: string;
}

export interface PoolStats {
  total_hashrate: string;
  active_workers: number;
  pool_fee: string;
  luck_1h: number;
  luck_24h: number;
  luck_7d: number;
}

export interface Block {
  height: number;
  timestamp: string;
  reward: string;
  hash: string;
}

export interface NotificationConfig {
  email?: string;
  sms?: string;
  worker_offline?: boolean;
  payout_received?: boolean;
  hashrate_drop?: boolean;
  hashrate_drop_threshold?: number;
}
