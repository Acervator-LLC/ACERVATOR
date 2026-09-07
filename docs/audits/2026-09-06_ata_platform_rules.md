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

Five more targets were read on **2026-09-07**: TikTok, Facebook, YouTube,
Threads and Reddit. Their sections sit below the four, in the same shape, and
every page they cite was read on that date.

Seven targets ship in the formatter after that read: X, Instagram, LinkedIn,
TikTok, Facebook, Threads and Reddit. TradingView and YouTube are not in the
set, each for a reason its own section states.

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

## TikTok

### Text — TikTok

A photo post carries a title and a description. TikTok states the title
"Maximum length is 90 in UTF-16 runes" and the description "Maximum length is
4000 in UTF-16 runes".
[Photo Post](https://developers.tiktok.com/doc/content-posting-api-reference-photo-post)

A video post carries a title only, and TikTok states "The maximum length is
2200 in UTF-16 runes" for it.
[Direct Post](https://developers.tiktok.com/doc/content-posting-api-reference-direct-post/)

**The 144-character header does not fit the 90-rune title.** The post body maps
to the description, which holds it. No artefact maps to the title.

**Budget: 4000 minus the 144-character header leaves 3856 runes.**

### Images — TikTok

TikTok accepts a still image post. The media types are "WebP" and "JPEG", the
size ceiling is "20MB for each image", and the picture ceiling is "1080p".
[Media Transfer Guide](https://developers.tiktok.com/doc/content-posting-api-media-transfer-guide)

The photo endpoint takes "An array containing up to 35 photo content URLs" and
a cover index starting from 0.
[Photo Post](https://developers.tiktok.com/doc/content-posting-api-reference-photo-post)

### Posting method — TikTok

`POST /v2/post/publish/content/init/` publishes a photo post. TikTok states
`media_type` is required and "Currently only PHOTO is allowed", and that
`post_mode` is `DIRECT_POST` or `MEDIA_UPLOAD`.
[Photo Post](https://developers.tiktok.com/doc/content-posting-api-reference-photo-post)

The scopes are "video.publish or video.upload", and the source field states
"Only PULL_FROM_URL is allowed" for a photo.
[Photo Post](https://developers.tiktok.com/doc/content-posting-api-reference-photo-post)

TikTok requires the developer to own the address the image is fetched from: "To
use PULL_FROM_URL as the content transfer method, developer must verify the
ownership of the URL prefix or domain."
[Photo Post](https://developers.tiktok.com/doc/content-posting-api-reference-photo-post)

Rate limit: "Each user access_token is limited to six requests per minute."
[Photo Post](https://developers.tiktok.com/doc/content-posting-api-reference-photo-post)

An unaudited client cannot publish in public: "All content posted by unaudited
clients will be restricted to private viewing mode."
[Get Started](https://developers.tiktok.com/doc/content-posting-api-get-started/)

Daily cap: TikTok caps how many posts one creator account takes through Direct
Post in a 24-hour window, and states "The upper limit may vary among creators
(typically around 15 posts per day/creator account)".
[Content Sharing Guidelines](https://developers.tiktok.com/doc/content-sharing-guidelines/)

### Content rules — TikTok

TikTok bans a watermark or a logo added by the integration: "API Clients should
not add promotional watermarks/logos to creators' content."
[Content Sharing Guidelines](https://developers.tiktok.com/doc/content-sharing-guidelines/)

The posting screen must name the account: "The upload page must display the
creator's nickname, so users are aware of which TikTok account the content will
be uploaded to."
[Content Sharing Guidelines](https://developers.tiktok.com/doc/content-sharing-guidelines/)

The privacy choice is the operator's and carries no default: "Users must
manually select the privacy status from a dropdown and there should be no
default value."
[Content Sharing Guidelines](https://developers.tiktok.com/doc/content-sharing-guidelines/)

Commercial content is disclosed through a toggle that is "turned off by
default", with a Your Brand option labelling the post "Promotional content" and
a Branded Content option labelling it "Paid partnership".
[Content Sharing Guidelines](https://developers.tiktok.com/doc/content-sharing-guidelines/)

### What is not published — TikTok

- No minimum title length and no minimum description length.
- No minimum pixel size and no aspect ratio for a photo.
- No rule about financial, investment or trading content on any developer page
  read here.
- The TikTok Community Guidelines pages returned a page title and no policy
  text to this reader on this date, so the frauds and scams rules could not be
  read from TikTok's own site.

## Facebook

### Text — Facebook

A Page post carries a message. Facebook describes it as "The main body of the
post. The message can contain mentions of Facebook Pages, `@[page-id]`."
[POST /{page-id}/feed](https://developers.facebook.com/docs/graph-api/reference/page/feed/)

Facebook states no maximum length for the message on that page. It states one
requirement: "Either `link` or `message` must be supplied."
[POST /{page-id}/feed](https://developers.facebook.com/docs/graph-api/reference/page/feed/)

A photo carries its own text field, which Facebook describes as "The
description of the photo".
[POST /{page-id}/photos](https://developers.facebook.com/docs/graph-api/reference/page/photos/)

### Images — Facebook

Formats: ".jpeg, .bmp, .png, .gif, .tiff".
[POST /{page-id}/photos](https://developers.facebook.com/docs/graph-api/reference/page/photos/)

File size: "Files can not exceed 10MB. For .png files, we recommend not
exceeding 1MB or the image may appear pixelated".
[POST /{page-id}/photos](https://developers.facebook.com/docs/graph-api/reference/page/photos/)

**Facebook takes the bytes.** The photo endpoint accepts a multipart upload,
and separately accepts "The URL of a photo that is already uploaded to the
Internet". A locally rendered image needs no public host.
[POST /{page-id}/photos](https://developers.facebook.com/docs/graph-api/reference/page/photos/)

Facebook rewrites what it receives: it "strips all location metadata before
publishing and resizes images to different dimensions".
[POST /{page-id}/photos](https://developers.facebook.com/docs/graph-api/reference/page/photos/)

### Posting method — Facebook

Publishing a text post is one call: "send a `POST` request to the
`/page_id/feed` endpoint". Publishing an image is one call to
`/page_id/photos`.
[Page posts](https://developers.facebook.com/docs/pages-api/posts)

Permissions on the feed call: a Page access token "requested by someone who can
perform the `CREATE_CONTENT` task on the Page", plus `pages_manage_posts`.
[POST /{page-id}/feed](https://developers.facebook.com/docs/graph-api/reference/page/feed/)

The photo call additionally names `pages_read_engagement` and
`pages_show_list`.
[POST /{page-id}/photos](https://developers.facebook.com/docs/graph-api/reference/page/photos/)

Rate limit: "Calls within 24 hours = 4800 * Number of Engaged Users", where
"Number of Engaged Users is the number of Users who engaged with the Page per
24 hours."
[Rate limiting](https://developers.facebook.com/docs/graph-api/overview/rate-limiting/)

An app token carries a separate ceiling: "Calls within one hour = 200 * Number
of Users".
[Rate limiting](https://developers.facebook.com/docs/graph-api/overview/rate-limiting/)

### Content rules — Facebook

Meta's fraud and scams policy bans content that "Offers investment
opportunities where returns on investment are guaranteed or risk-free".
[Fraud, scams and deceptive practices](https://transparency.meta.com/policies/community-standards/fraud-scams/)

Meta's spam policy names posting rate: "Posting, sharing, engaging with content
or creating accounts, Groups, Pages, Events or other assets, either manually or
automatically, at very high frequencies."
[Spam](https://transparency.meta.com/policies/community-standards/spam/)

Meta adds that it "may place restrictions on accounts that are acting at lower
frequencies when other indicators of Spam (e.g., posting repetitive content) or
signals of inauthenticity are present."
[Spam](https://transparency.meta.com/policies/community-standards/spam/)

**A Page rate that scales with engagement is a floor of zero.** A Page nobody
engages with earns no calls, so the first post of a new Page has the smallest
allowance.

### What is not published — Facebook

- No maximum length for the message on a Page post.
- No minimum image width, height or aspect ratio.
- No fixed numeric rate limit; the ceiling is a formula over engaged users.
- No rule naming financial or trading content beyond the fraud and scams
  policy, which is Meta-wide and not Facebook-specific.

## YouTube

### Text — YouTube

A video carries a title and a description. YouTube states the title "has a
maximum length of 100 characters and may contain all valid UTF-8 characters
except **<** and **>**", and the description "has a maximum length of 5000
bytes" with the same two characters excluded.
[Videos resource](https://developers.google.com/youtube/v3/docs/videos)

Tags carry their own ceiling: "The property value has a maximum length of 500
characters."
[Videos resource](https://developers.google.com/youtube/v3/docs/videos)

### Images — YouTube

**YouTube publishes no still image post.** The upload endpoint accepts
"video/\*, application/octet-stream" and nothing else.
[videos.insert](https://developers.google.com/youtube/v3/docs/videos/insert)

The API reference lists 21 resources: Activities, Captions, ChannelBanners,
Channels, ChannelSections, Comments, CommentThreads, I18nLanguages,
I18nRegions, Members, MembershipsLevels, PlaylistImages, PlaylistItems,
Playlists, Search, Subscriptions, Thumbnails, VideoAbuseReportReasons,
VideoCategories, Videos and Watermarks. None publishes a still image or a text
post to a channel.
[API reference](https://developers.google.com/youtube/v3/docs)

A thumbnail is not a post. It attaches to a video that already exists.
[Determine quota cost](https://developers.google.com/youtube/v3/determine_quota_cost)

### Posting method — YouTube

`POST https://www.googleapis.com/upload/youtube/v3/videos` uploads a video. The
maximum file size is "256GB".
[videos.insert](https://developers.google.com/youtube/v3/docs/videos/insert)

The authorization scopes are `https://www.googleapis.com/auth/youtube.upload`,
plus three wider ones the same page lists.
[videos.insert](https://developers.google.com/youtube/v3/docs/videos/insert)

Quota: "Projects that enable the YouTube Data API have a default quota
allocation of 100 `search.list` calls, 100 `videos.insert` calls, and 10,000
units per day combined for all other endpoints."
[Getting started](https://developers.google.com/youtube/v3/getting-started)

### Content rules — YouTube

The spam policy names investment schemes directly. It bans "Promoting 'get rich
quick' investment schemes, fake job offers, or sharing fake 'customer support'
contact information to steal private data".
[Spam, deceptive practices and scams](https://support.google.com/youtube/answer/2801973)

The same policy names machine-written volume: "Using automated tools or AI to
churn out high volumes of similar content with minimal changes".
[Spam, deceptive practices and scams](https://support.google.com/youtube/answer/2801973)

### What is not published — YouTube

- No route for publishing a still image as a post.
- No minimum title or description length.
- No community post endpoint anywhere in the Data API reference.

**YouTube is not a push target.** It publishes an API, and that API takes video
only. Phase 3 renders a still chart, so a post has no route in. It is removed
from the set for the same outcome as TradingView and a different reason:
TradingView publishes no API at all, and YouTube publishes one that takes
nothing ATA-SPM produces.

## Threads

### Text — Threads

"Text posts are limited to 500 characters." Emoji count as "the number of UTF-8
bytes".
[Threads posts](https://developers.facebook.com/docs/threads/posts)

**Budget: 500 minus the 144-character header leaves 356 characters.**

### Images — Threads

Formats: JPEG and PNG. Maximum file size: 8 MB. Aspect ratio ceiling: 10:1.
Width: minimum 320 pixels, maximum 1440 pixels.
[Threads posts](https://developers.facebook.com/docs/threads/posts)

The image must sit where Threads can fetch it: "it must be on a public server."
[Threads posts](https://developers.facebook.com/docs/threads/posts)

### Posting method — Threads

Publishing takes two calls. `POST /{threads-user-id}/threads` builds a
container and `POST /{threads-user-id}/threads_publish` publishes it.
[Threads posts](https://developers.facebook.com/docs/threads/posts)

The container names a media type, and the valid values are TEXT, IMAGE, VIDEO
and CAROUSEL.
[Threads posts](https://developers.facebook.com/docs/threads/posts)

Permissions: `threads_basic` on every endpoint, and `threads_content_publish`
to publish.
[Get started](https://developers.facebook.com/docs/threads/get-started)

Tokens: a short-lived token is "valid for 1 hour, but can be exchanged for
long-lived tokens", and a long-lived token is "valid for 60 days". A private
profile cannot extend a grant: "the permission grant cannot be extended and the
app user must grant the expired permission to your app again."
[Get started](https://developers.facebook.com/docs/threads/get-started)

Rate limit: "Profiles are limited to 250 published posts within a 24-hour
period."
[Threads posts](https://developers.facebook.com/docs/threads/posts)

### Content rules — Threads

Threads is a Meta surface and carries the Meta community standards. The fraud
and scams policy bans content that "Offers investment opportunities where
returns on investment are guaranteed or risk-free".
[Fraud, scams and deceptive practices](https://transparency.meta.com/policies/community-standards/fraud-scams/)

The spam policy names automatic posting "at very high frequencies".
[Spam](https://transparency.meta.com/policies/community-standards/spam/)

### What is not published — Threads

- No minimum text length.
- No minimum image height, and no minimum aspect ratio.
- No rule specific to financial or trading content on any Threads developer
  page.
- No stated container expiry on the posts page read here.

## Reddit

### Text — Reddit

A post names a title, and Reddit's own code caps it at 300 characters. The
validator reads `max_length = 300` and the reference text it generates reads
"title of the submission. up to %d characters long".
[VTitle, r2/r2/lib/validator/validator.py](https://raw.githubusercontent.com/reddit-archive/reddit/master/r2/r2/lib/validator/validator.py)

A self post carries body text, and the link model caps it: `SELFTEXT_MAX_LENGTH
= 40000`.
[r2/r2/models/link.py](https://raw.githubusercontent.com/reddit-archive/reddit/master/r2/r2/models/link.py)

**Budget: 300 minus the 144-character header leaves 156 characters of title**,
and 39,856 characters of body.

### Images — Reddit

The submit handler in Reddit's published source takes two kinds, and neither is
an image: `kind=VOneOf('kind', ['link', 'self'])`.
[POST_submit, r2/r2/controllers/api.py](https://raw.githubusercontent.com/reddit-archive/reddit/master/r2/r2/controllers/api.py)

That source is Reddit's archived open-source repository, not the live API
reference. **The live reference could not be read on this date.** An image
route may exist on the current API and is not proved here.

### Posting method — Reddit

`POST /api/submit` creates a post. Reddit's source guards it with
`@require_oauth2_scope("submit")` and validates the subreddit, the title, the
URL, the body and the kind.
[POST_submit, r2/r2/controllers/api.py](https://raw.githubusercontent.com/reddit-archive/reddit/master/r2/r2/controllers/api.py)

**A post must name a subreddit.** The subreddit validator refuses an empty
name, refuses a name that does not resolve, and refuses a user the subreddit
does not admit, answering SUBREDDIT_REQUIRED, SUBREDDIT_NOEXIST and
SUBREDDIT_NOTALLOWED in turn.
[VSubmitSR, r2/r2/lib/validator/validator.py](https://raw.githubusercontent.com/reddit-archive/reddit/master/r2/r2/lib/validator/validator.py)

The same validator takes the kind as a second argument, so the subreddit
decides whether a link post or a self post is admitted at all.
[VSubmitSR, r2/r2/lib/validator/validator.py](https://raw.githubusercontent.com/reddit-archive/reddit/master/r2/r2/lib/validator/validator.py)

Authentication: "Clients must authenticate with OAuth2". The authorization
endpoint is `https://www.reddit.com/api/v1/authorize` and the token endpoint is
`https://www.reddit.com/api/v1/access_token`.
[OAuth2](https://github.com/reddit-archive/reddit/wiki/OAuth2)

The scope list names `submit` among 19 scopes, and "All bearer tokens expire
after 1 hour."
[OAuth2](https://github.com/reddit-archive/reddit/wiki/OAuth2)

Rate limit: OAuth2 clients may make "up to 60 requests per minute", reported
back through three response headers.
[API](https://github.com/reddit-archive/reddit/wiki/API)

Reddit requires an honest client string in the format
`<platform>:<app ID>:<version string> (by /u/<reddit username>)`, and states
"NEVER lie about your user-agent."
[API](https://github.com/reddit-archive/reddit/wiki/API)

### Content rules — Reddit

**Reddit's own policy pages refused every read attempted here on this date.**
The API reference at `www.reddit.com/dev/api/`, the help centre article on the
Data API, and the Data API terms on `redditinc.com` all returned a refusal to
this reader. The self-promotion rules the operator asked about therefore have
no citation on this page.

What the API itself enforces is citable, and it is the stronger constraint: a
post names one subreddit, and that subreddit decides whether the account may
post and which kind is admitted.

### What is not published — Reddit

- The live API reference for `/api/submit`, which could not be read.
- The per-subreddit self-promotion rules, which live on each subreddit and not
  in the API documentation.
- Any image format, file size or dimension for a post, on the source read here.
- Any rule about financial or trading content, from a Reddit-owned page that
  answered this reader.

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

## Conflicts across the whole set

Seven targets ship. Each row names a constraint that forces a per-target
rendering, or a rule one target sets and the others do not.

| conflict | the clash |
|---|---|
| text length | After the 144-character header, X leaves 136 characters and Threads 356. Reddit leaves 156 in the title and 39,856 in the body. TikTok leaves 3,856 in the description. Instagram leaves 2,056 and LinkedIn about 2,856. Facebook publishes no ceiling. One body cannot serve a 136-character target and a 39,856-character one. |
| a field too small for the header | The header is 144 characters. TikTok's title accepts 90 runes, so the header cannot go in it. Reddit's title accepts 300, so the header leaves 156 characters for the call itself. |
| image delivery | Facebook, X and LinkedIn take the bytes. Instagram and Threads fetch the image from a public URL. TikTok fetches it from a URL on a domain the developer has verified with TikTok. A desktop application holds none of those hosts. |
| image format | Instagram accepts JPEG only. TikTok accepts WebP and JPEG. Threads accepts JPEG and PNG. Facebook accepts five formats. X accepts four. One render cannot be one file for all of them. |
| image size | X caps a still image at 5 MB, Facebook at 10 MB, Instagram and Threads at 8 MB, TikTok at 20 MB and 1080p, LinkedIn at 36,152,320 pixels. The smallest ceiling governs a single shared file. |
| still image accepted at all | YouTube takes video only, so a rendered chart has no route in. TradingView takes no upload at all. Both are outside the set. |
| a watermark | TikTok states an integration must not add a promotional watermark or logo. TradingView bans logos in content. The other targets state no such rule, and issue #407 offers a watermark as an option. |
| what the post must name | Reddit needs a subreddit, and that subreddit decides whether the account may post and which kind is admitted. No other target in the set names a destination inside the post. |
| automation disclosure | X requires a bot account to say it is a bot and name who runs it. TikTok requires the posting screen to show the creator's nickname and to take a privacy choice with no default. The others state no such requirement. |
| repeated wording | Phase 3 requires the same wording for the same condition. X bans "identical or substantially similar content across multiple accounts". Meta restricts repetitive content across Facebook, Instagram and Threads. YouTube's spam policy names automated high-volume similar content. |
| financial content | YouTube names investment schemes directly. Meta bans guaranteed or risk-free returns across Facebook, Instagram and Threads. X, LinkedIn and TikTok state no financial rule on the pages read. |
| rate limit shape | X publishes fixed numbers. Threads publishes 250 posts per 24 hours. TikTok publishes 6 requests per minute. Reddit publishes 60 requests per minute. Instagram publishes 100 posts per 24 hours. Facebook publishes a formula over engaged users, so a new Page starts near zero. LinkedIn publishes no number at all. |
| token lifetime | X issues a two-hour token. Reddit issues a one-hour token. Threads and Instagram issue a 60-day token that dies if it is not refreshed. A single refresh policy does not fit them. |
| documentation reachable | Reddit's own API reference, help centre and terms refused every read here. X's help pages refused two. Both platforms are in a set whose rule is that a limit with no citation is not a limit. |

## What the five add for the formatter

**One render still serves the set, at 1440 by 810 pixels.** That size is inside
TikTok's 1080p ceiling, inside the Threads width band of 320 to 1440, and
inside the Instagram width cap already recorded. JPEG serves Instagram, TikTok,
Threads, Facebook and X. PNG serves X, LinkedIn, Threads and Facebook.

**Three targets need a public address, not a file.** Instagram and Threads
fetch the image from a public server, and TikTok fetches it from a domain the
developer has verified. Facebook, X and LinkedIn take the bytes. Phase 5
records the first three as unreachable from a desktop application until the
operator supplies a host.

**Reddit needs one more value than every other target.** The subreddit is part
of the post, not part of the credential, and a post with no subreddit is
refused before it is written. The Settings page holds the credential; the
subreddit belongs beside the post.

**Two targets are outside the set, for two different reasons.** TradingView
publishes no API. YouTube publishes one that accepts video only. Neither is a
phase 5 failure to report, because neither is in the set.

**Measured on 2026-09-07** with the shipped formatter, one bullish call on
BTC-USD 1wk carrying two confirming voters: the body is 323 characters for X
and Threads, 369 for Instagram, 362 for LinkedIn, and 408 for TikTok, Facebook
and Reddit. **The X body is 43 characters over the 280 X publishes.** The
formatter applies no per-target ceiling, and the truncation rule below is
recorded and not built.

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
