-- Atomic token bucket.
-- KEYS[1] = bucket key
-- ARGV[1] = now_ms
-- ARGV[2] = capacity
-- ARGV[3] = refill_rate_per_ms
-- ARGV[4] = requested_tokens
--
-- Stored as a Redis hash:
--   tokens (float)
--   ts_ms  (int)
--
-- Returns array: {allowed(0/1), tokens_left, retry_after_ms}

local key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local refill_rate_per_ms = tonumber(ARGV[3])
local requested = tonumber(ARGV[4])

local data = redis.call('HMGET', key, 'tokens', 'ts_ms')
local tokens = tonumber(data[1])
local ts_ms = tonumber(data[2])

if tokens == nil or ts_ms == nil then
  tokens = capacity
  ts_ms = now_ms
end

local delta = now_ms - ts_ms
if delta < 0 then
  delta = 0
end

local refill = delta * refill_rate_per_ms
if refill > 0 then
  tokens = math.min(capacity, tokens + refill)
  ts_ms = now_ms
end

local allowed = 0
local retry_after_ms = 0

if tokens >= requested then
  allowed = 1
  tokens = tokens - requested
else
  local missing = requested - tokens
  if refill_rate_per_ms > 0 then
    retry_after_ms = math.ceil(missing / refill_rate_per_ms)
  else
    retry_after_ms = 0
  end
end

redis.call('HMSET', key, 'tokens', tokens, 'ts_ms', ts_ms)
-- Keep bucket keys from living forever (idle eviction). TTL ~= time-to-full + 60s.
local ttl_ms = math.floor((capacity / math.max(refill_rate_per_ms, 0.000001)) + 60000)
redis.call('PEXPIRE', key, ttl_ms)

return {allowed, tokens, retry_after_ms}
