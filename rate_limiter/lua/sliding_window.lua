-- Atomic sliding window log using a sorted set.
-- KEYS[1] = zset key
-- ARGV[1] = now_ms
-- ARGV[2] = window_size_ms
-- ARGV[3] = max_requests
--
-- Uses an INCR sequence key to create unique members.
-- Returns array: {allowed(0/1), remaining, retry_after_ms}

local key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local max_requests = tonumber(ARGV[3])

local cutoff = now_ms - window_ms
redis.call('ZREMRANGEBYSCORE', key, 0, cutoff)

local count = tonumber(redis.call('ZCARD', key))

if count < max_requests then
  local seq_key = key .. ':seq'
  local seq = redis.call('INCR', seq_key)
  local member = tostring(now_ms) .. '-' .. tostring(seq)
  redis.call('ZADD', key, now_ms, member)
  count = count + 1

  redis.call('PEXPIRE', key, window_ms)
  redis.call('PEXPIRE', seq_key, window_ms)

  local remaining = max_requests - count
  return {1, remaining, 0}
end

local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
local retry_after_ms = 0
if oldest[2] ~= nil then
  retry_after_ms = math.max(0, math.ceil(window_ms - (now_ms - tonumber(oldest[2]))))
end

return {0, 0, retry_after_ms}
