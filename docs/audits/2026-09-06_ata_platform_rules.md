# ATA-SPM push target rules

**Mode: Reference.** This page lists what each of the four ATA-SPM push
targets requires of a post. Phase 4 formats one post per target. These are the
limits that formatting must obey.

Every number below carries the page it came from. Each page was read on
**2026-09-06**. Platform limits change, so re-read the page before trusting a
number here.

Nothing was tested by posting. No account was used. No credential was used.

The four targets are TradingView, X, Instagram and LinkedIn, named in issue
#407.

## How to read the "not published" sections

A missing limit is a finding. Where a platform states no number, this page says
so and names the page that stays silent. A plausible number with no source does
not appear here.

Two pages of one platform can disagree. Where that happens, both are quoted and
both are named.

## The fixed header

Issue #407 fixes this text on every artefact that leaves the machine:

```
This is not investment advice. It is a demonstration of Ekthelius's
proprietary TA engine housed in the Acervator governance execution platform.
```

Measured length: **144 characters**. All characters are Latin letters,
punctuation or spaces. The header must never be truncated. Its length is the
first charge against every text budget below.

## TradingView

### Text — TradingView

A published idea requires a title, a description, a category, and a market
direction of long, neutral or short. Smart tags stay optional.
[How can I publish an idea?](https://www.tradingview.com/support/solutions/43000589083-how-can-i-publish-an-idea/)

TradingView asks for "a meaningful idea description that explains your analysis
and is helpful for other members to understand your reasoning".
[Publishing and updating ideas](https://www.tradingview.com/support/solutions/43000591338-publishing-and-updating-ideas/)

**No word minimum and no character minimum appear on either page.** The
operator asked whether TradingView sets a word minimum for a chart description.
TradingView publishes a quality instruction, not a count.

A published idea can be edited or deleted for 15 minutes only: "Public ideas
can be edited or removed only within 15 minutes after publishing."
[Publishing and updating ideas](https://www.tradingview.com/support/solutions/43000591338-publishing-and-updating-ideas/)

### Images — TradingView

An idea publishes the chart the author has open. Neither publishing page
documents an image upload field, an image format, a pixel size or a file size.

A locally rendered chart image has **no documented route into a TradingView
idea**.

### Posting method — TradingView

TradingView states: "We don't have an API that gives access to data as of now,
but we are planning to add it in the future." The same page states: "Our REST
API is meant for brokers who want to be supported on our trading platform."
[API access](https://www.tradingview.com/support/solutions/43000474413-i-need-access-to-your-api-in-order-to-get-data-or-indicator-values/)

Publishing runs through the website, using the publish button.
[How can I publish an idea?](https://www.tradingview.com/support/solutions/43000589083-how-can-i-publish-an-idea/)

**Phase 5 cannot send an idea to TradingView through a published API.** Phase 4
can still build the text and the chart. Phase 5 must record the target as
manual rather than fail without a message.

### Content rules — TradingView

House rule 2 bans promotion in all content. The banned list reads:
"all advertisements, logos, links or references to any website, social media,
messaging or email contacts, company names, wallet addresses, giveaways, prize
contests or any other kind of announcement or solicitation." Premium, Expert
and Ultimate subscribers may place contacts and links in the signature field
only.
[Our house rules](https://www.tradingview.com/support/solutions/43000591638-our-house-rules/)

House rule 8 asks authors to avoid "repeatedly sharing similar content".
[Our house rules](https://www.tradingview.com/support/solutions/43000591638-our-house-rules/)

House rule 4 requires the language of the TradingView subdomain in use.
[House rules](https://www.tradingview.com/house-rules/)

House rule 17 requires the author to warrant that published information
"doesn't constitute investment advice".
[House rules](https://www.tradingview.com/house-rules/)

A timeframe rule blocks short charts: "Ideas using a timeframe of less than 15
minutes can only be published privately or sent in chat or Minds."
[Publishing and updating ideas](https://www.tradingview.com/support/solutions/43000591338-publishing-and-updating-ideas/)

### What is not published — TradingView

- No minimum description length, in words or characters.
- No maximum title length and no maximum description length.
- No image format, pixel size or file size for an idea.
- No API for publishing an idea.
- No rate limit for publishing ideas.

## X

### Text — X

"Posts on X can contain up to 280 characters." Weight 1 covers Latin,
punctuation and common symbols. Weight 2 covers emoji, CJK characters and other
Unicode.
[Counting characters](https://docs.x.com/fundamentals/counting-characters)

"All URLs are wrapped with `t.co` shortener and count as 23 characters,
regardless of the original length."
[Counting characters](https://docs.x.com/fundamentals/counting-characters)

"Attached media (via official clients) counts as 0 characters."
[Counting characters](https://docs.x.com/fundamentals/counting-characters)

X names the `twitter-text` library for counting.
[Counting characters](https://docs.x.com/fundamentals/counting-characters)

The `text` field is "Required unless media is provided".
[Creation of a Post](https://docs.x.com/x-api/posts/creation-of-a-post)

**Budget: 280 minus the 144-character header leaves 136 characters.** One link
takes 23 of those and leaves 113.

### Images — X

Supported image types: "JPG, PNG, GIF, WEBP".
[Media best practices](https://docs.x.com/x-api/media/quickstart/best-practices)

"Image size: <= 5 MB". Animated GIF: "<= 15 MB".
[Media best practices](https://docs.x.com/x-api/media/quickstart/best-practices)

"You may attach up to 4 photos, 1 animated GIF or 1 video in a Post."
[Media best practices](https://docs.x.com/x-api/media/quickstart/best-practices)

The media category for a post image is `tweet_image`.
[Upload media](https://docs.x.com/x-api/media/upload-media)

### Posting method — X

`POST https://api.x.com/2/tweets` creates a post. It needs an OAuth 2.0 user
token carrying `tweet.write`, `tweet.read` and `users.read`. The `media` object
carries 1 to 4 `media_ids`.
[Creation of a Post](https://docs.x.com/x-api/posts/creation-of-a-post)

`POST /2/media/upload` uploads the image. It needs `media.write`. The image
travels as base64 in a JSON body or as raw bytes in a multipart body.
[Upload media](https://docs.x.com/x-api/media/upload-media)

An access token lasts "two hours unless you've used the `offline.access` scope".
The `offline.access` scope is what issues a refresh token.
[OAuth 2.0 authorization code](https://docs.x.com/resources/fundamentals/authentication/oauth-2-0/authorization-code)

Rate limit for creating a post: 10,000 per 24 hours per app, and 100 per 15
minutes per user.
[Rate limits](https://docs.x.com/x-api/fundamentals/rate-limits)

Cost: "The X API uses pay-per-usage pricing. No subscriptions—pay only for what
you use." Post creation costs $0.015 per request. A post carrying a URL costs
$0.200 per request.
[Pricing](https://docs.x.com/x-api/getting-started/pricing)

### Content rules — X

"Never post identical or substantially similar content across multiple
accounts."
[Developer policy](https://docs.x.com/developer-terms/policy)

"If you're operating an API-based bot account you must clearly indicate what
the account is and who is responsible for it." X suggests a statement in the
profile bio.
[Developer policy](https://docs.x.com/developer-terms/policy)

"Never perform bulk, aggressive, or spammy actions, including bulk following."
[Developer policy](https://docs.x.com/developer-terms/policy)

The restricted use cases list names no rule about financial, investment or
trading content.
[Restricted uses](https://docs.x.com/developer-terms/restricted-use-cases)

### What is not published — X

- Post caps for the named tiers are absent from the pricing page. That page now
  states pay-per-usage instead of tiers.
- No expiry for an uploaded `media_id`.
- No minimum and no maximum pixel size for a still image.
- No daily cap on organic posting inside the developer documentation.
- The counting page states 280 and names no longer limit for a paid account.
- `help.x.com` refused both reads attempted here with HTTP 403, so the X Rules
  and the automation help page could not be read from X's own site on this date.

## Instagram

### Text — Instagram

The caption parameter accepts "Maximum 2200 characters, 30 hashtags, and 20 @
tags."
[POST /{ig-user-id}/media](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media/)

An `alt_text` field exists for image posts from 24 March 2025.
[Content publishing](https://developers.facebook.com/docs/instagram-platform/content-publishing)

**Budget: 2200 minus the 144-character header leaves 2056 characters.**

### Images — Instagram

"JPEG is the only image format supported. Extended JPEG formats such as MPO and
JPS are not supported."
[Content publishing](https://developers.facebook.com/docs/instagram-platform/content-publishing)

File size: "8 MB maximum". Aspect ratio: "Must be within a 4:5 to 1.91:1
range". Minimum width 320 pixels, scaled up when smaller. Maximum width "1440
(will be scaled down to the maximum if necessary)". Colour space sRGB, converted
automatically.
[POST /{ig-user-id}/media](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media/)

The image must sit on a web server the platform can reach: "We will cURL the
image using the URL that you specify so the image must be on a public server."
[POST /{ig-user-id}/media](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media/)

Filters and shopping tags are unsupported.
[Content publishing](https://developers.facebook.com/docs/instagram-platform/content-publishing)

### Posting method — Instagram

Publishing takes two calls. `POST /<IG_ID>/media` builds a container. `POST
/<IG_ID>/media_publish` publishes it. `GET
/<IG_CONTAINER_ID>?fields=status_code` reports container status.
[Content publishing](https://developers.facebook.com/docs/instagram-platform/content-publishing)

The account must be a professional account.
[Overview](https://developers.facebook.com/docs/instagram-platform/overview)

Publishing needs `instagram_business_content_publish` under Instagram Login, or
`instagram_content_publish` with `instagram_basic` under Facebook Login. An app
serving accounts the developer does not own needs App Review, Advanced Access
and Business Verification.
[Overview](https://developers.facebook.com/docs/instagram-platform/overview)

Rate limit: "Instagram accounts are limited to 100 API-published posts within a
24-hour moving period." Carousel posts carry a separate limit of 50 within 24
hours. `GET /<IG_ID>/content_publishing_limit` reports current usage.
[Content publishing](https://developers.facebook.com/docs/instagram-platform/content-publishing)

Tokens: the authorization code lasts 1 hour and works once. The long-lived
token lasts 60 days. A refresh needs a token at least 24 hours old and the
`instagram_business_basic` permission. A token left unrefreshed for 60 days
expires and cannot be renewed.
[Business login](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/business-login)

### Content rules — Instagram

Meta's fraud and scams policy bans content that "Offers investment
opportunities where returns on investment are guaranteed or risk-free". It also
bans returns based on recruiting others, get-rich-quick offers, and money
flipping.
[Fraud, scams and deceptive practices](https://transparency.meta.com/policies/community-standards/fraud-scams/)

### What is not published — Instagram

- No minimum caption length.
- No minimum image height, and no pixel-count rule beyond the width and ratio
  bounds.
- The content publishing guide states the JPEG rule and the 100-post limit but
  states no caption, hashtag or mention counts. Those counts appear only on the
  media reference page.

## LinkedIn

### Text — LinkedIn

The Posts API schema marks `commentary` as required and typed as `little` text.
**The schema states no maximum length.**
[Post schema](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/post-api-schema)

The API does define an error for over-length text:
"FIELD_LENGTH_TOO_LONG — `{field}` length exceeds the allowed maximum. Reduce
the length of the `commentary` or other text fields."
[Posts API](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api)

LinkedIn's member help page states a number the API pages do not: "The
character limit for a post is 3,000 characters."
[Post and share updates](https://www.linkedin.com/help/linkedin/answer/a528176)

**Both pages belong to LinkedIn.** The help page is the only LinkedIn source
carrying a number, and it describes the website, not the API. Treat 3,000 as
the working ceiling and treat `FIELD_LENGTH_TOO_LONG` as the real test.

`commentary` uses the `little` text format. Reserved characters need a
backslash escape, "even if those characters are not used in one of the
supported elements or templates". The reserved set is
`| { } @ [ ] ( ) < > # \ * _ ~`.
[little text format](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/little-text-format)

`altText` on an image: "Maximum length is 4,086 characters, recommended length
is less than 120 characters."
[Images API](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/images-api)

**Budget: 3000 minus the 144-character header leaves 2856 characters**, before
escaping. Escaping grows the string, so the count sent is larger than the count
a reader sees.

### Images — LinkedIn

"The Images API supports the following image pixel count and formats: Images
with less than 36,152,320 pixels. JPG, GIF, and PNG formats. GIF format
supports up to 250 frames."
[Images API](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/images-api)

Upload takes two steps. `POST /rest/images?action=initializeUpload` returns an
`uploadUrl`, an `image` URN and an `uploadUrlExpiresAt` time. The bytes go to
the `uploadUrl`. The URN then goes into the post as `content.media.id`.
[Images API](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/images-api)

### Posting method — LinkedIn

`POST https://api.linkedin.com/rest/posts` creates a post. Two headers are
mandatory on every call: `Linkedin-Version: {YYYYMM}` and
`X-Restli-Protocol-Version: 2.0.0`. Success returns 201 with the post id in the
`x-restli-id` response header.
[Posts API](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api)

Permissions: `w_member_social` posts as a member. `w_organization_social` posts
as an organization and needs an ADMINISTRATOR, DIRECT_SPONSORED_CONTENT_POSTER
or CONTENT_ADMIN role on that page.
[Posts API](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api)

The API is versioned and versions expire. The Posts API page carries this
warning: "The Marketing Version 202508 (Marketing August 2025) will be sunset
on August 17, 2026."
[Posts API](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api)

Rate limits run per application and per member, over a 24-hour window that
resets at midnight UTC. Exceeding one returns 429.
[Rate limiting](https://learn.microsoft.com/en-us/linkedin/shared/api-guide/concepts/rate-limits)

### Content rules — LinkedIn

The Professional Community Policies name no rule for financial, investment or
market content. They do ban spam: "We don't allow untargeted, irrelevant,
obviously unwanted, unauthorized, inappropriate commercial or promotional, or
gratuitously repetitive messages or similar content."
[Professional community policies](https://www.linkedin.com/legal/professional-community-policies)

### What is not published — LinkedIn

- The maximum length of `commentary`, anywhere in the API documentation.
- Any image file size limit, aspect ratio or width bound. Only a pixel count
  appears.
- The numeric rate limits. LinkedIn states: "Standard rate limits are not
  published in documentation. You can look up the rate limit of any endpoint
  your app has access to through the Developer Portal."
  [Rate limiting](https://learn.microsoft.com/en-us/linkedin/shared/api-guide/concepts/rate-limits)
  An endpoint appears in that portal only after one live call, so the number
  cannot be read before the first post.

## Conflicts between the four targets

One post goes to four targets. No single format satisfies all four. Each row
names a constraint that forces a per-target rendering.

| conflict | the clash |
|---|---|
| text length | X allows 136 characters after the header. Instagram allows 2,056. LinkedIn allows about 2,856. TradingView states no cap. A body written for one is wrong for two others. |
| a link costs | On X a URL takes 23 characters and raises the request price from $0.015 to $0.200. TradingView house rule 2 bans links outright. |
| product naming | The fixed header names Ekthelius and Acervator. TradingView house rule 2 bans "logos ... company names" in content. The header is mandatory and the rule bans part of it. |
| watermark | A disclaimer watermark carries a logo or a name. TradingView bans logos in content. The other three place no such rule. |
| timeframe | TradingView blocks public ideas below a 15-minute timeframe. Issue #407 lists 5m as a crypto scan timeframe. A 5m call cannot go public on TradingView. |
| image format | Instagram accepts JPEG only, 8 MB, ratio 4:5 to 1.91:1, width 1440 maximum. LinkedIn and X accept PNG. TradingView accepts no upload at all. |
| image delivery | Instagram fetches the image from a public URL. X and LinkedIn accept the bytes directly. A locally rendered file cannot reach Instagram without a public host, and issue #407 forbids adding outbound surfaces to the render path. |
| repeated wording | Phase 3 requires the same wording for the same condition, every time. X bans "identical or substantially similar content across multiple accounts". TradingView house rule 8 warns against "repeatedly sharing similar content". |
| automation disclosure | X requires a bot account to say it is a bot and name who runs it. The other three state no such requirement. |
| language | TradingView requires the language of the subdomain in use. The other three state no language rule. |
| delivery route | Three targets publish through an API. TradingView publishes through its website only. Phase 5 has no send path for one of its four targets. |
| edit window | TradingView allows 15 minutes to correct a published idea. LinkedIn allows a partial update to `commentary` with no stated deadline. X and Instagram state no edit route for a published post. |

## What this settles for the formatter

**Never truncate.** The 144-character fixed header. On X it consumes over half
the budget.

**Truncate first.** The indicator explanations, longest first, then the gate
list. Keep the ticker, the direction and the timeframe.

**Pad nothing.** No target publishes a minimum length. The TradingView word
minimum the operator asked about does not exist as a published rule.

**Render once at 1440 by 810 pixels.** That ratio is 1.78, inside Instagram's
1.91 ceiling and its 1440 width cap. Save JPEG for Instagram at 8 MB or less.
Save PNG for X at 5 MB or less and for LinkedIn under 36,152,320 pixels.

**Report, never fail silently.** TradingView has no publishing API. Instagram
needs a public image URL the desktop application does not have. Both belong in
the phase 5 record as reported failures, matching the rule in issue #407 that a
target that cannot be reached is reported.

## Related

- Issue #407 defines the phases, the targets and the fixed header.
- `src/trading/ata_spm.py` holds the ATA-SPM phase code.
- `src/trading/ata_spm_push.py` holds the push target code.
