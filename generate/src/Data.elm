module Data exposing
    ( Flags
    , IndexInfo
    , Panel
    , Qualification
    , Row
    , agentName
    , currentPeriod
    , decodeFlags
    , findByPeriod
    , formatFixed2
    , formatPercent
    , isAgentSeries
    , isProvisional
    , latestByPeriod
    , latestPrint
    , seriesLabel
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


type alias Flags =
    { index : IndexInfo
    , prints : List Row
    , superseded : List Row
    , series : List Row
    , panel : Panel
    }


decodeFlags : Decoder Flags
decodeFlags =
    Decode.map5 Flags
        (Decode.field "index" decodeIndex)
        (Decode.field "prints" (Decode.list decodeRow))
        (Decode.field "superseded" (Decode.list decodeRow))
        (Decode.field "series" (Decode.list decodeRow))
        (Decode.field "panel" decodePanel)



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


findByPeriod : String -> List Row -> Maybe Row
findByPeriod period rows =
    rows
        |> List.filter (\row -> row.period == period)
        |> List.head


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

        whole =
            rounded // 100

        fractional =
            abs (rounded - whole * 100)
    in
    String.concat
        [ String.fromInt whole
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
