module ChartTest exposing (suite)

import Chart
import Data exposing (Row)
import Expect
import Html
import Test exposing (Test, describe, test)


baseRow : Row
baseRow =
    { period = "2026-09-14"
    , vintage = "1"
    , value = "23.4704"
    , denominator = "997"
    , coverage = "99.7"
    , provisional = "false"
    , methodologyVersion = "agents=1;protego=0.6.2"
    , collectorVersion = "f5c2b39"
    , computedAt = "2026-09-17T15:56:22Z"
    , reason = ""
    , seriesId = Nothing
    }


printRow : String -> String -> Row
printRow period value =
    { baseRow | period = period, value = value }


effectiveRow : String -> String -> Row
effectiveRow period value =
    { baseRow | period = period, value = value, seriesId = Just "effective" }


twoPeriodPrints : List Row
twoPeriodPrints =
    [ printRow "2026-09-07" "17.00"
    , printRow "2026-09-14" "23.47"
    ]


twoPeriodEffective : List Row
twoPeriodEffective =
    [ effectiveRow "2026-09-07" "20.00"
    , effectiveRow "2026-09-14" "29.00"
    ]


{-| 29 weekly periods, matching the shape (if not the exact dates) of the
real fixture used to eyeball this chart. One period midway through is
marked provisional, as it is in that fixture.
-}
manyPeriodPrints : List Row
manyPeriodPrints =
    List.range 0 28
        |> List.map
            (\n ->
                let
                    row =
                        printRow (weekOf n) (String.fromFloat (17.0 + toFloat n * 0.3))
                in
                case n == 18 of
                    True ->
                        { row | provisional = "true" }

                    False ->
                        row
            )


manyPeriodEffective : List Row
manyPeriodEffective =
    List.range 0 28
        |> List.map (\n -> effectiveRow (weekOf n) (String.fromFloat (20.0 + toFloat n * 0.3)))


{-| A synthetic but strictly increasing "YYYY-MM-DD" period label, so the
periods sort the same lexicographically as chronologically, as real
periods do.
-}
weekOf : Int -> String
weekOf n =
    let
        month =
            1 + n // 20

        day =
            1 + modBy 20 n
    in
    String.concat
        [ "2026-"
        , String.padLeft 2 '0' (String.fromInt month)
        , "-"
        , String.padLeft 2 '0' (String.fromInt day)
        ]


render : List Row -> List Row -> String
render prints series =
    Chart.view prints series
        |> List.map Html.toString
        |> String.concat


suite : Test
suite =
    describe "Chart"
        [ describe "degrading with fewer than two points"
            [ test "a single print renders a note and no svg" <|
                \_ ->
                    let
                        content =
                            render [ printRow "2026-09-14" "23.47" ] []
                    in
                    Expect.all
                        [ String.contains "begins once there are at least two published prints" >> Expect.equal True
                        , String.contains "<svg" >> Expect.equal False
                        ]
                        content
            , test "no prints at all also renders the note, not a chart" <|
                \_ ->
                    render [] []
                        |> String.contains "<svg"
                        |> Expect.equal False
            ]
        , describe "the chart with two or more periods"
            [ test "renders an accessible svg" <|
                \_ ->
                    render twoPeriodPrints twoPeriodEffective
                        |> String.contains "role=\"img\""
                        |> Expect.equal True
            , test "carries a title and a description" <|
                \_ ->
                    let
                        content =
                            render twoPeriodPrints twoPeriodEffective
                    in
                    Expect.all
                        [ String.contains "<title>" >> Expect.equal True
                        , String.contains "<desc>" >> Expect.equal True
                        ]
                        content
            , test "the description names both series by their trend" <|
                \_ ->
                    let
                        content =
                            render twoPeriodPrints twoPeriodEffective
                    in
                    Expect.all
                        [ String.contains "Targeted access rose" >> Expect.equal True
                        , String.contains "Effective access rose" >> Expect.equal True
                        ]
                        content
            , test "the y-axis includes a zero gridline" <|
                \_ ->
                    render twoPeriodPrints twoPeriodEffective
                        |> String.contains ">0%<"
                        |> Expect.equal True
            , test "the endpoint label carries the last targeted value" <|
                \_ ->
                    render twoPeriodPrints twoPeriodEffective
                        |> String.contains "23.47%"
                        |> Expect.equal True
            , test "the endpoint label carries the last effective value" <|
                \_ ->
                    render twoPeriodPrints twoPeriodEffective
                        |> String.contains "29.00%"
                        |> Expect.equal True
            , test "a legend names both series" <|
                \_ ->
                    let
                        content =
                            render twoPeriodPrints twoPeriodEffective
                    in
                    Expect.all
                        [ String.contains "Targeted" >> Expect.equal True
                        , String.contains "Effective" >> Expect.equal True
                        ]
                        content
            , test "no provisional legend note appears when nothing is provisional" <|
                \_ ->
                    render twoPeriodPrints twoPeriodEffective
                        |> String.contains "not yet finalised"
                        |> Expect.equal False
            ]
        , describe "provisional periods"
            [ test "a provisional period renders a hollow marker" <|
                \_ ->
                    render manyPeriodPrints manyPeriodEffective
                        |> String.contains "r=\"5\" fill=\"none\""
                        |> Expect.equal True
            , test "the legend explains the hollow marker" <|
                \_ ->
                    render manyPeriodPrints manyPeriodEffective
                        |> String.contains "not yet finalised"
                        |> Expect.equal True
            ]
        , describe "many periods"
            [ test "the x-axis is thinned, not one label per period" <|
                \_ ->
                    let
                        content =
                            render manyPeriodPrints manyPeriodEffective

                        labelCount =
                            String.indexes "class=\"chart-axis-label\"" content
                                |> List.length
                    in
                    -- one label per gridline plus a handful of x-axis labels;
                    -- far fewer than 29 periods worth of x labels.
                    (labelCount < 29)
                        |> Expect.equal True
            , test "the first and last periods are labelled on the x-axis" <|
                \_ ->
                    let
                        content =
                            render manyPeriodPrints manyPeriodEffective
                    in
                    Expect.all
                        [ String.contains (weekOf 0) >> Expect.equal True
                        , String.contains (weekOf 28) >> Expect.equal True
                        ]
                        content
            ]
        ]
