module Chart exposing (view, viewOne)

{-| Charts built from a `Row` series: `view`, the two-series chart on the
index pages, plotting the headline `targeted` figure (from `prints`)
against the broader `effective` figure (from the `effective` row of
`series`); and `viewOne`, a single-series chart for a crawler's own
history, where a second series and a legend would only add clutter a
section heading already covers.

This is inline SVG built by hand with `Html.node`, not a charting library —
the index page ships no JavaScript, and that is deliberate. A chart like
this would normally offer a hover crosshair and tooltip for the exact value
under the pointer; without JavaScript that is not available, so instead
every line ends in a direct-reading label for its last value, a legend
names each series where there is more than one, and the full series already
lives in a table elsewhere on the page. That is a compensation for a known
limitation, not an oversight.

-}

import Data exposing (Row)
import Dict exposing (Dict)
import Html exposing (Html)


{-| One parsed, period-and-value point from a `Row`, before it has been
placed on the chart's shared period axis.
-}
type alias Point =
    { period : String
    , value : Float
    , provisional : Bool
    }


{-| A `Point` once it has been given its position (`index`) on the shared
period axis, shared between both series so that a period lines up
vertically across them.
-}
type alias PlottedPoint =
    { index : Int
    , period : String
    , value : Float
    , provisional : Bool
    }


type alias YScale =
    { max : Float
    , step : Float
    }


{-| Render the trend section: a two-series chart with at least two periods,
or an honest note in its place when there are fewer than that. A single
point on axes is worse than no chart at all — the page's hero number
already carries the one-print case.

`cadence` names how often a period falls, e.g. `"weekly"` or `"quarterly"` —
it appears only in the chart's accessible title, since that is the one place
this reusable chart states an assumption about its caller's period length.

-}
view : { cadence : String } -> List Row -> List Row -> List Html
view config prints series =
    let
        targetedRaw =
            prints
                |> List.filterMap toPoint
                |> List.sortBy .period

        effectiveRaw =
            series
                |> List.filter isEffective
                |> List.filterMap toPoint
                |> List.sortBy .period
    in
    case List.length targetedRaw < 2 of
        True ->
            [ tooFewPointsNote ]

        False ->
            let
                indexByPeriod =
                    periodIndex (List.map .period targetedRaw)

                targeted =
                    plot indexByPeriod targetedRaw

                effective =
                    plot indexByPeriod effectiveRaw
            in
            [ chartSection config.cadence targeted effective ]


{-| Render a single-series chart: a token's own history, with at least two
periods, or the same honest note as `view` in its place when there are
fewer than that — a single point on axes is worse than no chart at all
here too. There is only ever one line, so there is no legend; `label`
names the series in the chart's accessible title and description, and the
caller's own section heading is what names it for a sighted reader.
-}
viewOne : { cadence : String, label : String } -> List Row -> List Html
viewOne config rows =
    let
        raw =
            rows
                |> List.filterMap toPoint
                |> List.sortBy .period
    in
    case List.length raw < 2 of
        True ->
            [ tooFewPointsParagraph ]

        False ->
            let
                indexByPeriod =
                    periodIndex (List.map .period raw)

                points =
                    plot indexByPeriod raw
            in
            [ singleChartFigure config.cadence config.label points ]


singleChartFigure : String -> String -> List PlottedPoint -> Html
singleChartFigure cadence label points =
    let
        periodCount =
            List.length points

        firstPeriod =
            points |> List.head |> Maybe.map .period |> Maybe.withDefault ""

        lastPeriod =
            points |> lastOf |> Maybe.map .period |> Maybe.withDefault ""

        yScale =
            yScaleFor (maxValueOf points)
    in
    Html.node "svg"
        [ Html.attribute "viewBox" (String.concat [ "0 0 ", svgFloat viewboxWidth, " ", svgFloat viewboxHeight ])
        , Html.attribute "class" "trend-chart"
        , Html.attribute "role" "img"
        ]
        (List.concat
            [ [ Html.node "title" [] [ Html.text (singleChartTitle label cadence periodCount firstPeriod lastPeriod) ]
              , Html.node "desc" [] [ Html.text (describeTrend label points) ]
              ]
            , List.map (gridlineRow yScale) (yTicks yScale)
            , xAxisLabels periodCount (List.map .period points)
            , [ seriesGroup colorTargeted periodCount yScale points ]
            , singleEndpointLabel periodCount yScale points
            ]
        )


singleChartTitle : String -> String -> Int -> String -> String -> String
singleChartTitle label cadence periodCount firstPeriod lastPeriod =
    String.concat
        [ label
        , " over time, "
        , String.fromInt periodCount
        , " "
        , cadence
        , " periods from "
        , firstPeriod
        , " to "
        , lastPeriod
        , "."
        ]


singleEndpointLabel : Int -> YScale -> List PlottedPoint -> List Html
singleEndpointLabel periodCount yScale points =
    case lastOf points of
        Nothing ->
            []

        Just point ->
            [ endpointLabel periodCount point (yPixelFor yScale point.value) ]


tooFewPointsNote : Html
tooFewPointsNote =
    Html.section [ Html.attribute "class" "trend" ]
        [ Html.h2 [] [ Html.text "Trend" ]
        , tooFewPointsParagraph
        ]


{-| The honest note in place of a chart with fewer than two points: a
single point on axes would be worse than no chart at all. Shared between
`view`, which wraps it in its own "Trend" section, and `viewOne`, whose
caller supplies its own heading.
-}
tooFewPointsParagraph : Html
tooFewPointsParagraph =
    Html.p [ Html.attribute "class" "meta" ]
        [ Html.text "The trend chart begins once there are at least two published prints." ]


isEffective : Row -> Bool
isEffective row =
    row.seriesId == Just "effective"


toPoint : Row -> Maybe Point
toPoint row =
    case String.toFloat row.value of
        Nothing ->
            Nothing

        Just value ->
            Just { period = row.period, value = value, provisional = Data.isProvisional row }


periodIndex : List String -> Dict String Int
periodIndex periods =
    periods
        |> List.indexedMap (\index period -> ( period, index ))
        |> Dict.fromList


plot : Dict String Int -> List Point -> List PlottedPoint
plot indexByPeriod points =
    points
        |> List.filterMap (plotOne indexByPeriod)
        |> List.sortBy .index


plotOne : Dict String Int -> Point -> Maybe PlottedPoint
plotOne indexByPeriod point =
    Dict.get point.period indexByPeriod
        |> Maybe.map (\index -> { index = index, period = point.period, value = point.value, provisional = point.provisional })


lastOf : List PlottedPoint -> Maybe PlottedPoint
lastOf points =
    points |> List.reverse |> List.head



-- Colours. Validated by a visualisation review; do not substitute.


colorTargeted : String
colorTargeted =
    "#2a78d6"


colorEffective : String
colorEffective =
    "#eb6834"


colorSurface : String
colorSurface =
    "#fdfdfb"


colorGrid : String
colorGrid =
    "#e3e2de"


colorInk : String
colorInk =
    "#1a1a1a"



-- Geometry. A fixed viewBox, scaled to the page width by CSS; the margins
-- leave room for the y-axis labels on the left, the x-axis labels along the
-- bottom, and the endpoint labels to the right of the last point, so
-- nothing is clipped.


viewboxWidth : Float
viewboxWidth =
    720


viewboxHeight : Float
viewboxHeight =
    360


marginLeft : Float
marginLeft =
    50


marginRight : Float
marginRight =
    96


marginTop : Float
marginTop =
    24


marginBottom : Float
marginBottom =
    40


plotWidth : Float
plotWidth =
    viewboxWidth - marginLeft - marginRight


plotHeight : Float
plotHeight =
    viewboxHeight - marginTop - marginBottom


{-| Round a value up to a "nice" scale maximum, always a multiple of a nice
step (1/2/5/10 times a power of ten) at least as large as the highest
value. The y-axis always starts at zero; this only ever decides the top.
-}
yScaleFor : Float -> YScale
yScaleFor maxValue =
    case maxValue <= 0 of
        True ->
            { max = 10, step = 10 }

        False ->
            let
                rawStep =
                    maxValue / 5

                magnitude =
                    10 ^ toFloat (floor (logBase 10 rawStep))

                normalized =
                    rawStep / magnitude

                step =
                    niceNormalizedStep normalized * magnitude

                steps =
                    ceiling (maxValue / step)
            in
            { max = step * toFloat steps, step = step }


niceNormalizedStep : Float -> Float
niceNormalizedStep normalized =
    [ 1, 2, 5, 10 ]
        |> List.filter (\candidate -> candidate >= normalized)
        |> List.head
        |> Maybe.withDefault 10


maxValueOf : List PlottedPoint -> Float
maxValueOf points =
    points
        |> List.map .value
        |> List.maximum
        |> Maybe.withDefault 0


yPixelFor : YScale -> Float -> Float
yPixelFor yScale value =
    marginTop + plotHeight * (1 - value / yScale.max)


xPixelFor : Int -> Int -> Float
xPixelFor periodCount index =
    case periodCount <= 1 of
        True ->
            marginLeft + plotWidth / 2

        False ->
            marginLeft + plotWidth * toFloat index / toFloat (periodCount - 1)


svgFloat : Float -> String
svgFloat value =
    String.fromFloat (roundTo 2 value)


roundTo : Int -> Float -> Float
roundTo decimals value =
    let
        factor =
            10 ^ toFloat decimals
    in
    toFloat (round (value * factor)) / factor



-- The chart itself.


chartSection : String -> List PlottedPoint -> List PlottedPoint -> Html
chartSection cadence targeted effective =
    let
        periodCount =
            List.length targeted

        firstPeriod =
            targeted |> List.head |> Maybe.map .period |> Maybe.withDefault ""

        lastPeriod =
            targeted |> lastOf |> Maybe.map .period |> Maybe.withDefault ""

        yScale =
            yScaleFor (maxValueOf (List.append targeted effective))

        hasProvisional =
            List.any .provisional (List.append targeted effective)
    in
    Html.section [ Html.attribute "class" "trend" ]
        [ Html.h2 [] [ Html.text "Trend" ]
        , chartFigure cadence periodCount yScale targeted effective firstPeriod lastPeriod
        , legend hasProvisional
        ]


chartFigure : String -> Int -> YScale -> List PlottedPoint -> List PlottedPoint -> String -> String -> Html
chartFigure cadence periodCount yScale targeted effective firstPeriod lastPeriod =
    Html.node "svg"
        [ Html.attribute "viewBox" (String.concat [ "0 0 ", svgFloat viewboxWidth, " ", svgFloat viewboxHeight ])
        , Html.attribute "class" "trend-chart"
        , Html.attribute "role" "img"
        ]
        (List.concat
            [ [ Html.node "title" [] [ Html.text (chartTitle cadence periodCount firstPeriod lastPeriod) ]
              , Html.node "desc" [] [ Html.text (trendDescription targeted effective) ]
              ]
            , List.map (gridlineRow yScale) (yTicks yScale)
            , xAxisLabels periodCount (List.map .period targeted)
            , [ seriesGroup colorTargeted periodCount yScale targeted
              , seriesGroup colorEffective periodCount yScale effective
              ]
            , endpointLabels periodCount yScale targeted effective
            ]
        )


chartTitle : String -> Int -> String -> String -> String
chartTitle cadence periodCount firstPeriod lastPeriod =
    String.concat
        [ "Targeted and effective access over time, "
        , String.fromInt periodCount
        , " "
        , cadence
        , " periods from "
        , firstPeriod
        , " to "
        , lastPeriod
        , "."
        ]


trendDescription : List PlottedPoint -> List PlottedPoint -> String
trendDescription targeted effective =
    String.concat
        [ describeTrend "Targeted access" targeted
        , " "
        , describeTrend "Effective access" effective
        ]


describeTrend : String -> List PlottedPoint -> String
describeTrend label points =
    case ( List.head points, lastOf points ) of
        ( Just first, Just last ) ->
            String.concat
                [ label
                , " "
                , trendWord first.value last.value
                , " from "
                , Data.formatFixed2 first.value
                , "% at "
                , first.period
                , " to "
                , Data.formatFixed2 last.value
                , "% at "
                , last.period
                , "."
                ]

        _ ->
            String.concat [ label, " has no data to describe." ]


trendWord : Float -> Float -> String
trendWord first last =
    case compare (abs (last - first)) 0.05 of
        GT ->
            case compare last first of
                GT ->
                    "rose"

                _ ->
                    "fell"

        _ ->
            "held steady"


yTicks : YScale -> List Int
yTicks yScale =
    List.range 0 (round (yScale.max / yScale.step))


gridlineRow : YScale -> Int -> Html
gridlineRow yScale tick =
    let
        value =
            toFloat tick * yScale.step

        y =
            yPixelFor yScale value
    in
    Html.node "g"
        [ Html.attribute "class" "chart-gridline" ]
        [ Html.node "line"
            [ Html.attribute "x1" (svgFloat marginLeft)
            , Html.attribute "x2" (svgFloat (marginLeft + plotWidth))
            , Html.attribute "y1" (svgFloat y)
            , Html.attribute "y2" (svgFloat y)
            , Html.attribute "stroke" colorGrid
            , Html.attribute "stroke-width" "1"
            ]
            []
        , Html.node "text"
            [ Html.attribute "x" (svgFloat (marginLeft - 8))
            , Html.attribute "y" (svgFloat y)
            , Html.attribute "text-anchor" "end"
            , Html.attribute "dominant-baseline" "middle"
            , Html.attribute "class" "chart-axis-label"
            ]
            [ Html.text (String.concat [ String.fromInt (round value), "%" ]) ]
        ]


{-| Thin 29 weekly periods down to a handful of readable x-axis labels: the
first and last periods always appear, with evenly spaced periods between
them so the axis never crowds.
-}
tickIndices : Int -> List Int
tickIndices periodCount =
    let
        desiredLabelCount =
            6
    in
    case periodCount <= desiredLabelCount of
        True ->
            List.range 0 (periodCount - 1)

        False ->
            let
                stride =
                    ceiling (toFloat (periodCount - 1) / toFloat (desiredLabelCount - 1))
            in
            List.range 0 (periodCount - 1)
                |> List.filter (\index -> modBy stride index == 0 || index == periodCount - 1)


xAxisLabels : Int -> List String -> List Html
xAxisLabels periodCount periods =
    tickIndices periodCount
        |> List.filterMap (\index -> List.head (List.drop index periods) |> Maybe.map (xAxisLabel periodCount index))


xAxisLabel : Int -> Int -> String -> Html
xAxisLabel periodCount index period =
    Html.node "text"
        [ Html.attribute "x" (svgFloat (xPixelFor periodCount index))
        , Html.attribute "y" (svgFloat (marginTop + plotHeight + 20))
        , Html.attribute "text-anchor" "middle"
        , Html.attribute "class" "chart-axis-label"
        ]
        [ Html.text period ]


seriesGroup : String -> Int -> YScale -> List PlottedPoint -> Html
seriesGroup color periodCount yScale points =
    Html.node "g"
        [ Html.attribute "class" "chart-series" ]
        (polylineFor color periodCount yScale points
            :: List.map (markerFor color periodCount yScale) points
        )


polylineFor : String -> Int -> YScale -> List PlottedPoint -> Html
polylineFor color periodCount yScale points =
    Html.node "polyline"
        [ Html.attribute "points" (pointsAttr periodCount yScale points)
        , Html.attribute "fill" "none"
        , Html.attribute "stroke" color
        , Html.attribute "stroke-width" "2"
        , Html.attribute "stroke-linejoin" "round"
        , Html.attribute "stroke-linecap" "round"
        ]
        []


pointsAttr : Int -> YScale -> List PlottedPoint -> String
pointsAttr periodCount yScale points =
    points
        |> List.map (\point -> String.concat [ svgFloat (xPixelFor periodCount point.index), ",", svgFloat (yPixelFor yScale point.value) ])
        |> String.join " "


{-| A data point marker. A provisional period gets a hollow ring instead of
a filled dot — the one visual cue on the chart that a value has not been
finalised; the legend explains what it means. An ordinary marker is filled
with the series colour and carries a ring in the surface colour, so it
stays legible where the two lines cross.
-}
markerFor : String -> Int -> YScale -> PlottedPoint -> Html
markerFor color periodCount yScale point =
    case point.provisional of
        True ->
            Html.node "circle"
                [ Html.attribute "cx" (svgFloat (xPixelFor periodCount point.index))
                , Html.attribute "cy" (svgFloat (yPixelFor yScale point.value))
                , Html.attribute "r" "5"
                , Html.attribute "fill" "none"
                , Html.attribute "stroke" color
                , Html.attribute "stroke-width" "2"
                ]
                []

        False ->
            Html.node "circle"
                [ Html.attribute "cx" (svgFloat (xPixelFor periodCount point.index))
                , Html.attribute "cy" (svgFloat (yPixelFor yScale point.value))
                , Html.attribute "r" "4"
                , Html.attribute "fill" color
                , Html.attribute "stroke" colorSurface
                , Html.attribute "stroke-width" "2"
                ]
                []


{-| The direct-reading label at the end of each line — the last value, and
nothing else. Text is always in ink, never in a series colour; the coloured
marker beside it already carries identity. When both lines end close
together, the labels are nudged apart so they never overlap.
-}
endpointLabels : Int -> YScale -> List PlottedPoint -> List PlottedPoint -> List Html
endpointLabels periodCount yScale targeted effective =
    case ( lastOf targeted, lastOf effective ) of
        ( Nothing, Nothing ) ->
            []

        ( Just t, Nothing ) ->
            [ endpointLabel periodCount t (yPixelFor yScale t.value) ]

        ( Nothing, Just e ) ->
            [ endpointLabel periodCount e (yPixelFor yScale e.value) ]

        ( Just t, Just e ) ->
            let
                minGap =
                    14

                ty =
                    yPixelFor yScale t.value

                ey =
                    yPixelFor yScale e.value

                gap =
                    abs (ty - ey)
            in
            case gap < minGap of
                False ->
                    [ endpointLabel periodCount t ty, endpointLabel periodCount e ey ]

                True ->
                    let
                        nudge =
                            (minGap - gap) / 2
                    in
                    case ty <= ey of
                        True ->
                            [ endpointLabel periodCount t (ty - nudge), endpointLabel periodCount e (ey + nudge) ]

                        False ->
                            [ endpointLabel periodCount t (ty + nudge), endpointLabel periodCount e (ey - nudge) ]


endpointLabel : Int -> PlottedPoint -> Float -> Html
endpointLabel periodCount point yPosition =
    Html.node "text"
        [ Html.attribute "x" (svgFloat (xPixelFor periodCount point.index + 10))
        , Html.attribute "y" (svgFloat yPosition)
        , Html.attribute "text-anchor" "start"
        , Html.attribute "dominant-baseline" "middle"
        , Html.attribute "class" "chart-endpoint-label"
        , Html.attribute "fill" colorInk
        ]
        [ Html.text (String.concat [ Data.formatFixed2 point.value, "%" ]) ]



-- The legend. Two series always need one; a provisional period adds a
-- third row explaining the hollow marker. This is not a second copy of the
-- series table further down the page — just enough text to read the chart.


legend : Bool -> Html
legend hasProvisional =
    Html.node "ul"
        [ Html.attribute "class" "chart-legend" ]
        (List.concat
            [ [ legendItem "chart-swatch-targeted" "Targeted — named crawler, disallowed"
              , legendItem "chart-swatch-effective" "Effective — named or blanket disallow"
              ]
            , provisionalLegendItem hasProvisional
            ]
        )


legendItem : String -> String -> Html
legendItem swatchClass label =
    Html.node "li"
        []
        [ Html.node "span" [ Html.attribute "class" (String.concat [ "chart-swatch ", swatchClass ]) ] []
        , Html.text label
        ]


provisionalLegendItem : Bool -> List Html
provisionalLegendItem hasProvisional =
    case hasProvisional of
        False ->
            []

        True ->
            [ Html.node "li"
                []
                [ Html.node "span" [ Html.attribute "class" "chart-swatch chart-swatch-provisional" ] []
                , Html.text "Hollow marker — provisional period, not yet finalised"
                ]
            ]
