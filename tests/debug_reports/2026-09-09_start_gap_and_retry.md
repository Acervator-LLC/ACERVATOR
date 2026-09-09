# Start All — the gap between bots, and one retry on a failed start

## The error

Three of 38 bots did not come up on the first attempt of the 8 September 2026
boot. The platform's own log carries the refusal three times and nothing else,
verbatim from `~/.acervator_logs/console/system.log.2`:

```
2026-09-08 11:10:43,649 [INFO] [COINBASE] BOT_CONNECT_FAILED | RateLimitExceeded:
coinbase GET https://api.coinbase.com/api/v3/brokerage/accounts?limit=250
429 Too Many Requests  | DIAGNOSIS: Rate limited. Application will retry after
delay. | Connection failed: ... | 0ms
2026-09-08 11:11:17,575 [INFO] [COINBASE] BOT_CONNECT_FAILED | RateLimitExceeded: ...
2026-09-08 11:11:40,263 [INFO] [COINBASE] BOT_CONNECT_FAILED | RateLimitExceeded: ...
```

The three bots are SUI/USD, ALLO/USDC and PUMP/USD. The first pass logs 35
`starting on` lines in fleet order with a hole at each of those three positions,
and each hole costs 15.3 to 16.5 seconds against a 3.8 to 7.2 second norm. All
three were started again at 11:21, eight minutes later.

## Reproduction

How many boots were read, and what they hold:

```
~/.acervator_logs/console/system.log .1 .2 .3 .4 .5     5 files, 2026-09-07 to 09
  boots present (38 "Restored bot" lines each)          3  (.5, .3, .2)
  boots with a fleet start sequence                     1  (.2, 2026-09-08 11:09)
  first-attempt failures in that boot                   3  of 38
~/.acervator_logs/console_*.log                         126 launch captures
  carrying 429 Too Many Requests                        52
  carrying any bot start or connect record              0
```

The rate is measured on one boot: 3 of 38, 7.9 per cent, which matches the
operator's "on average three random bots fail to start".

`main.py` cannot be launched while the platform is trading — the instance guard
at `main.py:812` writes into `~/.acervator`, the live process's tree. The
sequence was therefore run by calling `BotManager.start_all` on a fleet of
`BotContainer` subclasses, under `python -X dev -X faulthandler` with
`PYTHONWARNINGS=error`, and every observation below is read off the lines the
platform's own `acervator.bot` logger wrote. Nothing in this unit times, counts
or measures the code; the timestamps and the counts are the program's.

## The cause

`BotManager.start_all` in `src/trading/bot_container.py` waited
`min_gap_seconds = 0.6` between bots. At that spacing the boot fires its exchange
calls faster than Coinbase allows. The same log window carries
`CCXT call queue at capacity (8/8) for coinbase` and repeated
`RateLimitExceeded on get_balances (attempt 1/3), retrying in 1.0s`, so the
existing in-call retries are already exhausted before a bot's connect is
refused.

The failure is transient. At 11:10:43,649 the SUI connect was refused with a
429; at 11:10:51,559 a `FETCH_OHLCV` call on the same symbol returned 300
candles. The same call succeeded eight seconds later, with no change but time.

That is what puts the retry immediately in place rather than in a pass at the
end. One gap plus one verification window is 13.5 seconds, comfortably past the
window the 429 held, and the bot keeps its position in the sequence. A tail pass
would leave the bot idle for the rest of the boot — which is the cost the
operator is already paying, since his own manual retry came eight minutes later.

There was also no log line at all for a bot that fails. `bot_timeout` went to the
event bus only, so the boot above left a silent hole where three bots should be.

## The correction

`START_ALL_GAP_SECONDS = 3.5` in `src/trading/container/config.py`, the module
`bot_container.py` already imports its tunables from. 3.5 is the midpoint of the
operator's 3-to-4-second range, clear of both ends. `start_all` takes it as the
`min_gap_seconds` default and `start_all_progress_surface.py` composes the
dialog caption from the same name, so the caption cannot state a figure the
engine does not use.

The verification poll moved into `BotManager._await_running` unchanged, so the
first attempt and the retry share one body. A bot that does not reach RUNNING is
stopped and started once more, then the sequence continues whatever the result.

```python
            verified = await self._await_running(bot, verify_timeout_seconds)
            if not verified and not getattr(self, "_start_all_cancel", False):
                logger.warning(
                    "Bot %s did not reach RUNNING in %.1fs; retrying once",
                    bot.bot_id,
                    verify_timeout_seconds,
                )
                # stop() first: start() on a STARTING bot returns without
                # replacing the task, so a bare second start does nothing.
                await asyncio.sleep(min_gap_seconds)
                await bot.stop()
                await bot.start()
                verified = await self._await_running(bot, verify_timeout_seconds)
```

The `stop()` is load-bearing. `BotContainer.start` returns early on RUNNING or
STARTING, and a bot that failed verification is left in STARTING, so a bare
second `start()` logs `already running` and creates no task. `stop()` then
`start()` is the pair `_on_bot_command`'s own `restart` already runs.

## The rerun

Every line below is the platform's own output.

**The gap.** Eight consecutive start-to-start intervals, read off the
timestamps the logger wrote:

```
15:09:22,104 Bot HEALTHY1 starting on HEALTHY1/USD
15:09:25,874 Bot HEALTHY2 starting on HEALTHY2/USD      3.770
15:09:29,652 Bot HEALTHY3 starting on HEALTHY3/USD      3.778
15:09:33,423 Bot HEALTHY4 starting on HEALTHY4/USD      3.771
15:09:37,201 Bot HEALTHY5 starting on HEALTHY5/USD      3.778
15:09:40,967 Bot HEALTHY6 starting on HEALTHY6/USD      3.766
15:09:44,747 Bot LATEBOT  starting on LATEBOT/USD       3.780
15:10:02,399 Bot HEALTHY7 starting on HEALTHY7/USD      3.752  (from the retry)
15:10:06,170 Bot DEADBOT  starting on DEADBOT/USD       3.771
```

min 3.752, max 3.780, every interval inside 3.0 to 4.0 seconds.

**The retry fires.** LATEBOT reaches RUNNING only after it has been stopped and
started again:

```
15:09:44,747 [INFO]    Bot LATEBOT starting on LATEBOT/USD
15:09:55,135 [WARNING] Bot LATEBOT did not reach RUNNING in 10.0s; retrying once
15:09:58,647 [INFO]    Bot LATEBOT stopped
15:09:58,647 [INFO]    Bot LATEBOT starting on LATEBOT/USD
15:10:02,399 [INFO]    Bot HEALTHY7 starting on HEALTHY7/USD
```

Two `starting on` lines, no timeout line, and the next bot 3.752 seconds later.

**The retry is single.** DEADBOT never reaches RUNNING and is tried exactly
twice:

```
15:10:06,170 [INFO]    Bot DEADBOT starting on DEADBOT/USD
15:10:16,598 [WARNING] Bot DEADBOT did not reach RUNNING in 10.0s; retrying once
15:10:20,106 [INFO]    Bot DEADBOT stopped
15:10:20,106 [INFO]    Bot DEADBOT starting on DEADBOT/USD
15:10:30,495 [WARNING] Bot DEADBOT is not RUNNING after 10.0s; start_all moved on
15:10:34,010 [INFO]    Bot HEALTHY8 starting on HEALTHY8/USD
```

Two `starting on` lines, never a third, and HEALTHY8 starts after it.

**The control.** `git stash push -- src/trading/bot_container.py` restored the
0.6 default and removed the retry. The same fleet, the same driver:

```
15:10:58,099 Bot HEALTHY1 starting on HEALTHY1/USD
15:10:58,966 Bot HEALTHY2 starting on HEALTHY2/USD      0.867
15:10:59,824 Bot HEALTHY3 starting on HEALTHY3/USD      0.858
15:11:00,689 Bot HEALTHY4 starting on HEALTHY4/USD      0.865
15:11:01,553 Bot HEALTHY5 starting on HEALTHY5/USD      0.864
15:11:02,424 Bot HEALTHY6 starting on HEALTHY6/USD      0.871
15:11:03,297 Bot LATEBOT  starting on LATEBOT/USD       0.873
15:11:14,310 Bot HEALTHY7 starting on HEALTHY7/USD     11.013
15:11:15,173 Bot DEADBOT  starting on DEADBOT/USD       0.863
15:11:26,247 Bot HEALTHY8 starting on HEALTHY8/USD     11.074
```

One `starting on` line for LATEBOT, one for DEADBOT, no warning of any kind, and
the interval back to 0.6 plus the poll. The change is what produces both the
3.5-second spacing and the retry.

## Boot time

Gaps alone. 38 bots run 37 waits, since the loop skips the wait after the last
bot:

```
37 x 0.6 =  22.2 s
37 x 3.5 = 129.5 s        an increase of 107.3 s
```

Assumption: 38 eligible bots, gaps only, no verification wait and no retry.

Against the real boot. The 8 September pass ran 11:09:24 to 11:12:57, 212.9
seconds for 35 bots, mean interval 6.263 seconds and 5.318 seconds excluding the
three failure holes. A bot's own verification therefore cost 4.72 seconds on
average at a 0.6 gap:

```
per bot at 0.6      5.318 s        37 waits ->  3 min 17 s
per bot at 3.5      8.218 s        37 waits ->  5 min 04 s
three retries       +13.5 s each               +    40 s
                                   total   -> ~5 min 45 s
```

Assumption: the measured 4.72 second mean verification time holds, and three
bots still fail their first attempt. Before this change those three did not
trade until they were restarted by hand eight minutes in.

## What the program's own output could not answer

Three of the four observations came from the logger's existing lines. The
verdict a bot that fails twice receives did not: `bot_timeout` reached the event
bus and no log handler. That is fixed in this unit by the two warnings above, so
all four now read off the platform's own output.

## Found and not fixed

`BotManager.start_all` calls no exchange connect, while `_on_bot_command`'s
`start` calls `_connect_exchange_for_bot` first — the three measured 429s were
raised on that path, so a bot whose connector never attaches reaches `start_all`
unable to trade. Named only; changing what a start does is outside this unit.
