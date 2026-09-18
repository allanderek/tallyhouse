module PagesTest exposing (suite)

import Data exposing (Flags, Panel, Row)
import Expect
import Pages
import Set
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


basePanel : Panel
basePanel =
    { trancoListId = "N2P2W"
    , captured = "2026-09-17T15:47:47Z"
    , size = 1000
    , qualification =
        { candidatesExamined = 1600
        , excluded = 556
        , qualified = 1000
        , knownBias = "sites behind anti-automation challenges are excluded and are plausibly more AI-hostile than average, so the panel likely under-represents AI-hostile sites"
        , rule = "first N domains of the Tranco list returning a conclusive robots.txt observation during the sweep"
        }
    }


baseFlags : Flags
baseFlags =
    { index =
        { id = "agent-accessibility"
        , title = "Agent Accessibility Index"
        , question = "How many of the top 1000 websites tell AI crawlers to stay out?"
        }
    , prints = [ baseRow ]
    , superseded = []
    , series =
        [ { baseRow | value = "16.349", seriesId = Just "agent:GPTBot" }
        , { baseRow | value = "5.8175", seriesId = Just "blanket" }
        ]
    , panel = basePanel
    }


agentAccessibilityContent : Flags -> String
agentAccessibilityContent flags =
    Pages.pages flags
        |> List.filter (\page -> page.path == "agent-accessibility/index.html")
        |> List.map .content
        |> String.concat


aboutContent : Flags -> String
aboutContent flags =
    Pages.pages flags
        |> List.filter (\page -> page.path == "about/index.html")
        |> List.map .content
        |> String.concat


suite : Test
suite =
    describe "Pages"
        [ describe "emitted paths"
            [ test "emits exactly the three expected relative paths" <|
                \_ ->
                    Pages.pages baseFlags
                        |> List.map .path
                        |> Expect.equal
                            [ "index.html"
                            , "agent-accessibility/index.html"
                            , "about/index.html"
                            ]
            , test "no path is emitted twice" <|
                \_ ->
                    let
                        paths =
                            List.map .path (Pages.pages baseFlags)
                    in
                    Set.size (Set.fromList paths)
                        |> Expect.equal (List.length paths)
            , test "no path has a leading slash" <|
                \_ ->
                    Pages.pages baseFlags
                        |> List.map .path
                        |> List.all (\path -> not (String.startsWith "/" path))
                        |> Expect.equal True
            ]
        , describe "provisional prints"
            [ test "a provisional print is marked provisional on the index page" <|
                \_ ->
                    let
                        flags =
                            { baseFlags | prints = [ { baseRow | provisional = "true" } ] }
                    in
                    agentAccessibilityContent flags
                        |> String.contains "PROVISIONAL"
                        |> Expect.equal True
            , test "a final print is not marked provisional" <|
                \_ ->
                    agentAccessibilityContent baseFlags
                        |> String.contains "PROVISIONAL"
                        |> Expect.equal False
            ]
        , describe "restatements"
            [ test "a superseded vintage produces the restatement section" <|
                \_ ->
                    let
                        flags =
                            { baseFlags
                                | prints = [ { baseRow | vintage = "2", value = "23.4704", reason = "corrected a parser bug" } ]
                                , superseded = [ { baseRow | vintage = "1", value = "20.0000" } ]
                            }

                        content =
                            agentAccessibilityContent flags
                    in
                    Expect.all
                        [ String.contains "Restated periods" >> Expect.equal True
                        , String.contains "20.00%" >> Expect.equal True
                        , String.contains "23.47%" >> Expect.equal True
                        , String.contains "corrected a parser bug" >> Expect.equal True
                        ]
                        content
            , test "an empty superseded list produces no restatement section" <|
                \_ ->
                    agentAccessibilityContent baseFlags
                        |> String.contains "Restated periods"
                        |> Expect.equal False
            ]
        , describe "series grouping"
            [ test "agent series and fixed series are shown under separate headings" <|
                \_ ->
                    let
                        content =
                            agentAccessibilityContent baseFlags
                    in
                    Expect.all
                        [ String.contains "Fixed series" >> Expect.equal True
                        , String.contains "Per-agent series" >> Expect.equal True
                        , String.contains "GPTBot" >> Expect.equal True
                        , String.contains "Blanket disallow" >> Expect.equal True
                        ]
                        content
            , test "an agent series is labelled by its bare crawler name, not its raw series id" <|
                \_ ->
                    agentAccessibilityContent baseFlags
                        |> String.contains "agent:GPTBot"
                        |> Expect.equal False
            ]
        , describe "the panel's known bias"
            [ test "appears on the index page" <|
                \_ ->
                    agentAccessibilityContent baseFlags
                        |> String.contains basePanel.qualification.knownBias
                        |> Expect.equal True
            ]
        , describe "the Tranco link on the about page"
            [ test "links to the Tranco site" <|
                \_ ->
                    aboutContent baseFlags
                        |> String.contains "<a href=\"https://tranco-list.eu/\">Tranco</a>"
                        |> Expect.equal True
            , test "links the panel id to its specific list, using the id from flags" <|
                \_ ->
                    aboutContent baseFlags
                        |> String.contains
                            (String.concat
                                [ "<a href=\"https://tranco-list.eu/list/"
                                , basePanel.trancoListId
                                , "\">"
                                , basePanel.trancoListId
                                , "</a>"
                                ]
                            )
                        |> Expect.equal True
            ]
        , describe "the coverage explanation on the index page"
            [ test "explains that coverage is the share of the panel conclusively observed" <|
                \_ ->
                    agentAccessibilityContent baseFlags
                        |> String.contains "share of the panel this period"
                        |> Expect.equal True
            , test "explains that excluded sites are dropped from both numerator and denominator" <|
                \_ ->
                    agentAccessibilityContent baseFlags
                        |> String.contains "excluded from both the numerator and the denominator"
                        |> Expect.equal True
            ]
        ]
