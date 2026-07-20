export type InboxItemStatus = "unread" | "read" | "saved" | "dismissed";

export type ContentSubscription = {
  id: string;
  user_id: string;
  name: string;
  source_type: "rss";
  feed_url: string;
  normalized_feed_url: string;
  enabled: boolean;
  last_refresh_status: "never" | "success" | "partial" | "failed";
  last_refresh_at: string | null;
  last_success_at: string | null;
  last_error_code: string | null;
  created_at: string;
  updated_at: string;
};

export type InboxItemSource = {
  subscription_id: string;
  source_name: string;
  feed_entry_id: string | null;
  discovered_at: string;
};

export type InboxItem = {
  id: string;
  user_id: string;
  canonical_url: string | null;
  title: string;
  excerpt: string;
  author: string | null;
  published_at: string | null;
  fetched_at: string;
  content_hash: string;
  status: InboxItemStatus;
  sources: InboxItemSource[];
  created_at: string;
  updated_at: string;
};

export type InboxPage = {
  items: InboxItem[];
  next_cursor: string | null;
};

export type InboxSummary = {
  subscription_count: number;
  enabled_subscription_count: number;
  unread_count: number;
  saved_count: number;
  last_refresh_at: string | null;
  last_refresh_status: string | null;
};

export type RefreshResult = {
  status: "success" | "partial" | "unavailable" | "failed";
  subscription_id: string | null;
  fetched_count: number;
  created_count: number;
  duplicate_count: number;
  invalid_count: number;
  source_link_count: number;
  fetched_at: string;
  limitations: string[];
  error_code: string | null;
};

export type RefreshAllResult = {
  status: RefreshResult["status"];
  results: RefreshResult[];
  fetched_count: number;
  created_count: number;
  duplicate_count: number;
  invalid_count: number;
  source_link_count: number;
  fetched_at: string;
};

export type OPMLImportResult = {
  created_count: number;
  existing_count: number;
  invalid_count: number;
  rejected_count: number;
  subscriptions: ContentSubscription[];
  errors: string[];
};
