module Data exposing
    ( Agent
    , Crawl
    , CrawlEndpoint
    , Crawler
    , DivergentDomain
    , Download
    , Flags
    , History
    , HistoryPanel
    , IndexInfo
    , Operator
    , Panel
    , PanelConstruction
    , Qualification
    , Row
    , Stances
    , agentHistory
    , agentName
    , biggestMove
    , currentPeriod
    , decodeFlags
    , downloadsFor
    , earliestPrint
    , findByPeriod
    , findBySeriesAndPeriod
    , firstBlockedPeriod
    , formatFixed2
    , formatPercent
    , humanBytes
    , isAgentSeries
    , isProvisional
    , latestByPeriod
    , latestPrint
    , purposeLabel
    , seriesLabel
    , stancesTotal
    )

{-| The shapes of the site data, and the pure helpers the pages are built
from.

Every field on a `Row` is a `String`, even the ones that look like numbers or
booleans. That is deliberate: the ledger this data comes from is a CSV, kept
as strings so a round trip through it can never change a published value.
Anything that needs to be a number or a boolean is converted here, at the
edge, rather than trusted to arrive that way.

-}

import Dict exposing (Dict)
import Json.Decode as Decode exposing (Decoder)


{-| Apply a decoded function to a decoded value. `Json.Decode` tops out at
`map8`, which is not enough fields for `Row`, so this is the usual way to
decode a record with more fields than that using only `elm/json`.
-}
andMap : Decoder a -> Decoder (a -> b) -> Decoder b
andMap =
    Decode.map2 (|>)


{-| One row of `prints.csv` or `series.csv`. `seriesId` is `Nothing` for a
`prints` or `superseded` row, and `Just "agent:GPTBot"` (or `Just "blanket"`,
and so on) for a `series` row.
-}
type alias Row =
    { period : String
    , vintage : String
    , value : String
    , denominator : String
    , coverage : String
    , provisional : String
    , methodologyVersion : String
    , collectorVersion : String
    , computedAt : String
    , reason : String
    , seriesId : Maybe String
    }


decodeRow : Decoder Row
decodeRow =
    Decode.succeed Row
        |> andMap (Decode.field "period" Decode.string)
        |> andMap (Decode.field "vintage" Decode.string)
        |> andMap (Decode.field "value" Decode.string)
        |> andMap (Decode.field "denominator" Decode.string)
        |> andMap (Decode.field "coverage" Decode.string)
        |> andMap (Decode.field "provisional" Decode.string)
        |> andMap (Decode.field "methodology_version" Decode.string)
        |> andMap (Decode.field "collector_version" Decode.string)
        |> andMap (Decode.field "computed_at" Decode.string)
        |> andMap (Decode.field "reason" Decode.string)
        |> andMap (Decode.maybe (Decode.field "series_id" Decode.string))


type alias IndexInfo =
    { id : String
    , title : String
    , question : String
    }


decodeIndex : Decoder IndexInfo
decodeIndex =
    Decode.map3 IndexInfo
        (Decode.field "id" Decode.string)
        (Decode.field "title" Decode.string)
        (Decode.field "question" Decode.string)


{-| The panel's own account of how it was assembled, including the stated
bias. `knownBias` is the sentence that must appear on the index page: sites
behind anti-automation challenges are excluded from the panel, and are
plausibly more AI-hostile than average, so the headline likely understates
the true figure.
-}
type alias Qualification =
    { candidatesExamined : Int
    , excluded : Int
    , qualified : Int
    , knownBias : String
    , rule : String
    }


decodeQualification : Decoder Qualification
decodeQualification =
    Decode.map5 Qualification
        (Decode.field "candidates_examined" Decode.int)
        (Decode.field "excluded" Decode.int)
        (Decode.field "qualified" Decode.int)
        (Decode.field "known_bias" Decode.string)
        (Decode.field "rule" Decode.string)


type alias Panel =
    { trancoListId : String
    , captured : String
    , size : Int
    , qualification : Qualification
    }


decodePanel : Decoder Panel
decodePanel =
    Decode.map4 Panel
        (Decode.field "tranco_list_id" Decode.string)
        (Decode.field "captured" Decode.string)
        (Decode.field "size" Decode.int)
        (Decode.field "qualification" decodeQualification)


{-| The four ways a site can treat one crawler token in robots.txt, each
holding a domain count. `Unmentioned` is not consent: the file simply never
names the token, which does not rule out a blanket rule catching it anyway.
-}
type alias Stances =
    { fullBlock : Int
    , partialBlock : Int
    , allowed : Int
    , unmentioned : Int
    }


decodeStances : Decoder Stances
decodeStances =
    Decode.map4 Stances
        (Decode.field "FullBlock" Decode.int)
        (Decode.field "PartialBlock" Decode.int)
        (Decode.field "Allowed" Decode.int)
        (Decode.field "Unmentioned" Decode.int)


{-| Total domains counted across all four stances for one crawler.
-}
stancesTotal : Stances -> Int
stancesTotal stances =
    stances.fullBlock + stances.partialBlock + stances.allowed + stances.unmentioned


{-| One tracked crawler or consent token. `seriesId` names the row in
`Flags.series` carrying its published rate; the rate is never recomputed
from `stances`, which is descriptive only.
-}
type alias Agent =
    { token : String
    , slug : String
    , operator : String
    , purpose : String
    , description : String
    , seriesId : String
    , stances : Stances
    }


decodeAgent : Decoder Agent
decodeAgent =
    Decode.map7 Agent
        (Decode.field "token" Decode.string)
        (Decode.field "slug" Decode.string)
        (Decode.field "operator" Decode.string)
        (Decode.field "purpose" Decode.string)
        (Decode.field "description" Decode.string)
        (Decode.field "series_id" Decode.string)
        (Decode.field "stances" decodeStances)


{-| One domain that does not treat an operator's tokens alike, e.g. training
disallowed while search is allowed. `stances` maps each of the operator's
token names to that domain's stance for it.
-}
type alias DivergentDomain =
    { domain : String
    , stances : Dict String String
    }


decodeDivergentDomain : Decoder DivergentDomain
decodeDivergentDomain =
    Decode.map2 DivergentDomain
        (Decode.field "domain" Decode.string)
        (Decode.field "stances" (Decode.dict Decode.string))


{-| The operator behind one or more tokens. `divergentExamples` is a capped
sample; `divergentCount` is the true total, always shown alongside the
sample when it is capped, so a reader is never left wondering how many were
left out.
-}
type alias Operator =
    { name : String
    , description : String
    , tokens : List String
    , divergentCount : Int
    , divergentExamples : List DivergentDomain
    }


decodeOperator : Decoder Operator
decodeOperator =
    Decode.map5 Operator
        (Decode.field "name" Decode.string)
        (Decode.field "description" Decode.string)
        (Decode.field "tokens" (Decode.list Decode.string))
        (Decode.field "divergent_count" Decode.int)
        (Decode.field "divergent_examples" (Decode.list decodeDivergentDomain))


{-| One endpoint of the historical panel's construction: a Tranco list this
project drew a membership snapshot from, so a reader can go check who was on
the list at that date rather than trust the retained count on its own.
-}
type alias CrawlEndpoint =
    { trancoListId : String
    , date : String
    , size : Int
    }


decodeCrawlEndpoint : Decoder CrawlEndpoint
decodeCrawlEndpoint =
    Decode.map3 CrawlEndpoint
        (Decode.field "tranco_list_id" Decode.string)
        (Decode.field "date" Decode.string)
        (Decode.field "size" Decode.int)


{-| How the historical panel was assembled, and its stated limits.
`notComparable` is the sentence that must appear anywhere the live and
historical indices are mentioned together: they measure different
populations, so a level on one is not a level on the other.
-}
type alias PanelConstruction =
    { rule : String
    , churn : String
    , knownBias : String
    , notComparable : String
    , retained : Int
    }


decodePanelConstruction : Decoder PanelConstruction
decodePanelConstruction =
    Decode.map5 PanelConstruction
        (Decode.field "rule" Decode.string)
        (Decode.field "churn" Decode.string)
        (Decode.field "known_bias" Decode.string)
        (Decode.field "not_comparable" Decode.string)
        (Decode.field "retained" Decode.int)


{-| The historical index's panel: the 611 domains present at both ends of a
three-year span, rather than a single dated snapshot the way the live
index's panel is.
-}
type alias HistoryPanel =
    { size : Int
    , endpoints : List CrawlEndpoint
    , construction : PanelConstruction
    }


decodeHistoryPanel : Decoder HistoryPanel
decodeHistoryPanel =
    Decode.map3 HistoryPanel
        (Decode.field "size" Decode.int)
        (Decode.field "endpoints" (Decode.list decodeCrawlEndpoint))
        (Decode.field "construction" decodePanelConstruction)


{-| One Common Crawl archive this index reads from: its own crawl id, the
quarter-ish period it stands for, and a human name for that window.
-}
type alias Crawl =
    { crawl : String
    , period : String
    , name : String
    }


decodeCrawl : Decoder Crawl
decodeCrawl =
    Decode.map3 Crawl
        (Decode.field "crawl" Decode.string)
        (Decode.field "period" Decode.string)
        (Decode.field "name" Decode.string)


{-| The three-year quarterly series read from Common Crawl's archive — a
second index alongside the live weekly one, over a different panel and
gathered a different way, so it carries its own title, question and panel
rather than borrowing the live index's.
-}
type alias History =
    { id : String
    , title : String
    , question : String
    , prints : List Row
    , superseded : List Row
    , series : List Row
    , panel : HistoryPanel
    , crawls : List Crawl
    , selection : String
    }


decodeHistory : Decoder History
decodeHistory =
    Decode.succeed History
        |> andMap (Decode.field "id" Decode.string)
        |> andMap (Decode.field "title" Decode.string)
        |> andMap (Decode.field "question" Decode.string)
        |> andMap (Decode.field "prints" (Decode.list decodeRow))
        |> andMap (Decode.field "superseded" (Decode.list decodeRow))
        |> andMap (Decode.field "series" (Decode.list decodeRow))
        |> andMap (Decode.field "panel" decodeHistoryPanel)
        |> andMap (Decode.field "crawls" (Decode.list decodeCrawl))
        |> andMap (Decode.field "selection" Decode.string)


{-| The crawler's own published identity: the exact user-agent it sends, the
bot-verification token and category, a human-readable purpose statement, a
contact point, and the egress addresses every request originates from.
`prefixes` entries are CIDR notation (IPv4 or IPv6) and may be `[]` — a
checkout without `data/crawler.json` must still render a crawler page, just
one that says no address list is published yet.
-}
type alias Crawler =
    { userAgent : String
    , token : String
    , category : String
    , purpose : String
    , contact : String
    , prefixes : List String
    }


decodeCrawler : Decoder Crawler
decodeCrawler =
    Decode.map6 Crawler
        (Decode.field "userAgent" Decode.string)
        (Decode.field "token" Decode.string)
        (Decode.field "category" Decode.string)
        (Decode.field "purpose" Decode.string)
        (Decode.field "contact" Decode.string)
        (Decode.field "prefixes" (Decode.list Decode.string))


{-| One CSV file published alongside the site: where it lives (relative to
the site root, not to whichever page links it), which index it belongs to,
a human label and description, and its size so a reader knows what they are
about to fetch before they click. The content itself never reaches this
program — Python writes the bytes directly, and the generator only renders
the link.

`indexId` is `""` when the file belongs to both indices (the two ledgers
hold every index's rows, distinguished by an `index_id` column inside the
file) and a specific index's id when the file belongs to that index alone —
see `downloadsFor`.

-}
type alias Download =
    { path : String
    , indexId : String
    , label : String
    , description : String
    , bytes : Int
    , rows : Int
    }


decodeDownload : Decoder Download
decodeDownload =
    Decode.succeed Download
        |> andMap (Decode.field "path" Decode.string)
        |> andMap (Decode.field "indexId" Decode.string)
        |> andMap (Decode.field "label" Decode.string)
        |> andMap (Decode.field "description" Decode.string)
        |> andMap (Decode.field "bytes" Decode.int)
        |> andMap (Decode.field "rows" Decode.int)


{-| The downloads one index's page may offer: those shared between every
index (`indexId == ""`) plus those owned by the given index id, in the
order they arrived. A download owned by a different index is dropped —
the live index's panel and the historical index's panel are different
populations, so a page must never offer the other index's panel or
verdicts file.
-}
downloadsFor : String -> List Download -> List Download
downloadsFor indexId downloads =
    List.filter (\download -> download.indexId == "" || download.indexId == indexId) downloads


type alias Flags =
    { index : IndexInfo
    , prints : List Row
    , superseded : List Row
    , series : List Row
    , panel : Panel
    , agents : Dict String Agent
    , operators : Dict String Operator
    , purposes : Dict String String
    , history : History
    , crawler : Crawler
    , downloads : List Download
    }


decodeFlags : Decoder Flags
decodeFlags =
    Decode.succeed Flags
        |> andMap (Decode.field "index" decodeIndex)
        |> andMap (Decode.field "prints" (Decode.list decodeRow))
        |> andMap (Decode.field "superseded" (Decode.list decodeRow))
        |> andMap (Decode.field "series" (Decode.list decodeRow))
        |> andMap (Decode.field "panel" decodePanel)
        |> andMap (Decode.field "agents" (Decode.dict decodeAgent))
        |> andMap (Decode.field "operators" (Decode.dict decodeOperator))
        |> andMap (Decode.field "purposes" (Decode.dict Decode.string))
        |> andMap (Decode.field "history" decodeHistory)
        |> andMap (Decode.field "crawler" decodeCrawler)
        |> andMap (Decode.field "downloads" (Decode.list decodeDownload))



-- Predicates and small conversions.


isProvisional : Row -> Bool
isProvisional row =
    row.provisional == "true"


isAgentSeries : Row -> Bool
isAgentSeries row =
    case row.seriesId of
        Nothing ->
            False

        Just seriesId ->
            String.startsWith "agent:" seriesId


{-| The crawler's name, with the `agent:` prefix stripped. Only meaningful
when `isAgentSeries` is `True`; returns `""` for anything else.
-}
agentName : Row -> String
agentName row =
    case row.seriesId of
        Nothing ->
            ""

        Just seriesId ->
            String.dropLeft (String.length "agent:") seriesId


{-| A human label for one of the fixed (non-agent) series ids.
-}
seriesLabel : String -> String
seriesLabel seriesId =
    case seriesId of
        "blanket" ->
            "Blanket disallow (closed to every crawler)"

        "coverage" ->
            "Coverage"

        "effective" ->
            "Effective (named or blanket)"

        "unreadable" ->
            "Unreadable robots.txt"

        other ->
            other


vintageOf : Row -> Int
vintageOf row =
    Maybe.withDefault 0 (String.toInt row.vintage)


{-| The most recent period among the given rows, by lexicographic order on
the `YYYY-MM-DD` period string. `Nothing` if the list is empty.
-}
currentPeriod : List Row -> Maybe String
currentPeriod rows =
    rows
        |> List.map .period
        |> List.sort
        |> List.reverse
        |> List.head


{-| The row for the current period, from a list of prints already reduced to
one row per period.
-}
latestPrint : List Row -> Maybe Row
latestPrint rows =
    case currentPeriod rows of
        Nothing ->
            Nothing

        Just period ->
            findByPeriod period rows


{-| The earliest of the given rows by period, comparing period strings rather
than trusting the list's own order. `Nothing` if the list is empty. Used on a
historical series, which arrives already ordered, so this is a belt-and-braces
check rather than a substitute for sorting it.
-}
earliestPrint : List Row -> Maybe Row
earliestPrint rows =
    rows
        |> List.sortBy .period
        |> List.head


{-| Of the rows whose `seriesId` is `Just "change_since_previous"`, the one
with the greatest numeric `value` — the single biggest step in a historical
series. `Nothing` if there are none, so nobody has to hardcode which period
that step fell on.
-}
biggestMove : List Row -> Maybe Row
biggestMove rows =
    rows
        |> List.filter (\row -> row.seriesId == Just "change_since_previous")
        |> List.filterMap withNumericValue
        |> List.sortBy Tuple.first
        |> List.reverse
        |> List.head
        |> Maybe.map Tuple.second


withNumericValue : Row -> Maybe ( Float, Row )
withNumericValue row =
    String.toFloat row.value
        |> Maybe.map (\value -> ( value, row ))


findByPeriod : String -> List Row -> Maybe Row
findByPeriod period rows =
    rows
        |> List.filter (\row -> row.period == period)
        |> List.head


{-| The row for one series id and one period, e.g. `agent:GPTBot` for the
current period — the published rate for one crawler.
-}
findBySeriesAndPeriod : String -> String -> List Row -> Maybe Row
findBySeriesAndPeriod seriesId period rows =
    rows
        |> List.filter (\row -> row.seriesId == Just seriesId && row.period == period)
        |> List.head


{-| One token's three-year history: the rows for `"agent:" ++ token` in a
historical series, ordered by period. `[]` if the token has no historical
rows at all, e.g. a crawler that history predates.
-}
agentHistory : String -> List Row -> List Row
agentHistory token rows =
    rows
        |> List.filter (\row -> row.seriesId == Just (String.concat [ "agent:", token ]))
        |> List.sortBy .period


{-| The earliest period, among the given rows, whose value is greater than
zero — roughly when a crawler became known enough that sites started naming
it. `Nothing` if every row is zero (or the list is empty), rather than the
first row regardless of its value: a later zero must not hide an earlier
non-zero reading, nor may a token that was never blocked be reported as
blocked from its first period.
-}
firstBlockedPeriod : List Row -> Maybe String
firstBlockedPeriod rows =
    rows
        |> List.filterMap withNumericValue
        |> List.filter (\( value, _ ) -> value > 0)
        |> List.map (\( _, row ) -> row.period)
        |> List.sort
        |> List.head


{-| A human label for an agent's `purpose` category.
-}
purposeLabel : String -> String
purposeLabel purpose =
    case purpose of
        "training" ->
            "Training"

        "user-initiated" ->
            "User-initiated"

        "search" ->
            "Search"

        "training-consent" ->
            "Training consent"

        "data-broker" ->
            "Data broker"

        "archive" ->
            "Archive"

        "images" ->
            "Images"

        "mixed" ->
            "Mixed"

        "uncertain" ->
            "Uncertain"

        other ->
            other


{-| Reduce a list that may hold several vintages of the same period down to
the highest vintage per period. Used on `superseded`, which is not
pre-reduced the way `prints` and `series` are: a restated period can carry
more than one earlier vintage, and the one worth showing is the one
immediately before the current value.
-}
latestByPeriod : List Row -> List Row
latestByPeriod rows =
    rows
        |> List.foldl keepHighestVintage Dict.empty
        |> Dict.values


keepHighestVintage : Row -> Dict String Row -> Dict String Row
keepHighestVintage row acc =
    case Dict.get row.period acc of
        Nothing ->
            Dict.insert row.period row acc

        Just existing ->
            case vintageOf row > vintageOf existing of
                False ->
                    acc

                True ->
                    Dict.insert row.period row acc



-- Formatting. Values arrive as strings like "23.4704"; displayed figures are
-- rounded to two decimal places rather than shown at full ledger precision.


formatFixed2 : Float -> String
formatFixed2 value =
    let
        rounded =
            round (value * 100)

        sign =
            case rounded < 0 of
                True ->
                    "-"

                False ->
                    ""

        magnitude =
            abs rounded

        whole =
            magnitude // 100

        fractional =
            magnitude - whole * 100
    in
    String.concat
        [ sign
        , String.fromInt whole
        , "."
        , String.padLeft 2 '0' (String.fromInt fractional)
        ]


{-| Render a ledger value string as a rounded percentage, e.g. `"23.4704"` to
`"23.47%"`. Falls back to the raw string if it does not parse as a number,
rather than hiding a bad value behind a blank.
-}
formatPercent : String -> String
formatPercent raw =
    case String.toFloat raw of
        Nothing ->
            raw

        Just value ->
            String.concat [ formatFixed2 value, "%" ]


{-| A file size in binary units (1 KB = 1024 bytes), the way a reader expects
a download's size to be shown. Below 1024 bytes it is a bare byte count;
above that it is KB or MB to one decimal place.

The unit is chosen from the raw byte count, not from the rounded figure, so a
size just under 1 MB (e.g. `1048575`) is reported as `"1024.0 KB"` rather
than being bumped up to `"1.0 MB"`. That reads a little oddly right at the
boundary, but it keeps the rule simple and the output a pure function of the
input with no second rounding pass to get wrong.

-}
humanBytes : Int -> String
humanBytes bytes =
    case bytes < 1024 of
        True ->
            String.concat [ String.fromInt bytes, " B" ]

        False ->
            case bytes < 1024 * 1024 of
                True ->
                    String.concat [ oneDecimal (toFloat bytes / 1024), " KB" ]

                False ->
                    String.concat [ oneDecimal (toFloat bytes / (1024 * 1024)), " MB" ]


{-| A `Float` rounded to one decimal place, e.g. `2.47265625` to `"2.5"`.
Mirrors `formatFixed2`'s approach (scale, round to an `Int`, split whole from
fractional) rather than relying on `Float` string formatting, which Elm's
core libraries do not provide.
-}
oneDecimal : Float -> String
oneDecimal value =
    let
        rounded =
            round (value * 10)

        whole =
            rounded // 10

        fractional =
            rounded - whole * 10
    in
    String.concat [ String.fromInt whole, ".", String.fromInt fractional ]
