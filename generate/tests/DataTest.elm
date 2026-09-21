module DataTest exposing (suite)

import Data exposing (Row)
import Dict
import Expect
import Json.Decode as Decode
import Test exposing (Test, describe, test)


{-| A trimmed version of a real flags document (same shape produced by
`tallyhouse.site.load_site_data`), kept small enough to read at a glance.
Every ledger-derived value is a string, on purpose - the decoders must not
assume otherwise.
-}
sampleJson : String
sampleJson =
    """
    { "index": { "id": "agent-accessibility", "title": "Agent Accessibility Index", "question": "How many of the top 1000 websites tell AI crawlers to stay out?" }
    , "prints":
        [ { "index_id": "agent-accessibility", "period": "2026-09-14", "vintage": "1", "value": "23.4704", "denominator": "997", "coverage": "99.7", "provisional": "false", "methodology_version": "agents=1;protego=0.6.2", "collector_version": "f5c2b39", "computed_at": "2026-09-17T15:56:22Z", "reason": "" }
        ]
    , "superseded": []
    , "series":
        [ { "index_id": "agent-accessibility", "period": "2026-09-14", "vintage": "1", "value": "16.349", "denominator": "997", "coverage": "99.7", "provisional": "false", "methodology_version": "agents=1;protego=0.6.2", "collector_version": "f5c2b39", "computed_at": "2026-09-17T15:56:22Z", "reason": "", "series_id": "agent:GPTBot" }
        , { "index_id": "agent-accessibility", "period": "2026-09-14", "vintage": "1", "value": "5.8175", "denominator": "997", "coverage": "99.7", "provisional": "false", "methodology_version": "agents=1;protego=0.6.2", "collector_version": "f5c2b39", "computed_at": "2026-09-17T15:56:22Z", "reason": "", "series_id": "blanket" }
        ]
    , "panel":
        { "tranco_list_id": "N2P2W"
        , "captured": "2026-09-17T15:47:47Z"
        , "size": 1000
        , "qualification":
            { "candidates_examined": 1600
            , "excluded": 556
            , "excluded_by_outcome": { "Challenged": 35, "ConnectFailure": 283 }
            , "known_bias": "sites behind anti-automation challenges are excluded and are plausibly more AI-hostile than average, so the panel likely under-represents AI-hostile sites"
            , "qualified": 1000
            , "rule": "first N domains of the Tranco list returning a conclusive robots.txt observation during the sweep"
            }
        }
    , "agents":
        { "GPTBot":
            { "token": "GPTBot"
            , "slug": "gptbot"
            , "operator": "OpenAI"
            , "purpose": "training"
            , "description": "Collects web content to train OpenAI's generative models."
            , "series_id": "agent:GPTBot"
            , "stances": { "FullBlock": 126, "PartialBlock": 37, "Allowed": 33, "Unmentioned": 801 }
            }
        }
    , "operators":
        { "OpenAI":
            { "name": "OpenAI"
            , "description": "Operates three separately-named tokens for three different jobs."
            , "tokens": [ "GPTBot" ]
            , "divergent_count": 0
            , "divergent_examples": []
            }
        }
    , "purposes":
        { "training": "Bulk crawling to build model training data." }
    }
    """


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


suite : Test
suite =
    describe "Data"
        [ describe "decodeFlags"
            [ test "decodes a real flags document" <|
                \_ ->
                    Decode.decodeString Data.decodeFlags sampleJson
                        |> Result.map .index
                        |> Expect.equal (Ok { id = "agent-accessibility", title = "Agent Accessibility Index", question = "How many of the top 1000 websites tell AI crawlers to stay out?" })
            , test "string fields stay strings, including value and provisional" <|
                \_ ->
                    Decode.decodeString Data.decodeFlags sampleJson
                        |> Result.map (\flags -> List.map (\row -> ( row.value, row.provisional )) flags.prints)
                        |> Expect.equal (Ok [ ( "23.4704", "false" ) ])
            , test "a series row decodes its series_id" <|
                \_ ->
                    Decode.decodeString Data.decodeFlags sampleJson
                        |> Result.map (\flags -> List.map .seriesId flags.series)
                        |> Expect.equal (Ok [ Just "agent:GPTBot", Just "blanket" ])
            , test "a print row has no series_id" <|
                \_ ->
                    Decode.decodeString Data.decodeFlags sampleJson
                        |> Result.map (\flags -> List.map .seriesId flags.prints)
                        |> Expect.equal (Ok [ Nothing ])
            , test "the panel's known bias decodes as a plain string" <|
                \_ ->
                    Decode.decodeString Data.decodeFlags sampleJson
                        |> Result.map (\flags -> flags.panel.qualification.knownBias)
                        |> Expect.equal (Ok "sites behind anti-automation challenges are excluded and are plausibly more AI-hostile than average, so the panel likely under-represents AI-hostile sites")
            , test "the panel's size decodes as a real number, not a string" <|
                \_ ->
                    Decode.decodeString Data.decodeFlags sampleJson
                        |> Result.map (\flags -> flags.panel.size)
                        |> Expect.equal (Ok 1000)
            , test "an agent's stance counts decode as integers" <|
                \_ ->
                    Decode.decodeString Data.decodeFlags sampleJson
                        |> Result.map (\flags -> Dict.get "GPTBot" flags.agents |> Maybe.map .stances)
                        |> Expect.equal (Ok (Just { fullBlock = 126, partialBlock = 37, allowed = 33, unmentioned = 801 }))
            , test "an operator's tokens and divergent examples decode" <|
                \_ ->
                    Decode.decodeString Data.decodeFlags sampleJson
                        |> Result.map (\flags -> Dict.get "OpenAI" flags.operators |> Maybe.map .tokens)
                        |> Expect.equal (Ok (Just [ "GPTBot" ]))
            , test "purposes decode as a map from category to explanation" <|
                \_ ->
                    Decode.decodeString Data.decodeFlags sampleJson
                        |> Result.map (\flags -> Dict.get "training" flags.purposes)
                        |> Expect.equal (Ok (Just "Bulk crawling to build model training data."))
            ]
        , describe "isProvisional"
            [ test "\"true\" is provisional" <|
                \_ ->
                    Data.isProvisional { baseRow | provisional = "true" }
                        |> Expect.equal True
            , test "\"false\" is not provisional" <|
                \_ ->
                    Data.isProvisional { baseRow | provisional = "false" }
                        |> Expect.equal False
            ]
        , describe "isAgentSeries and agentName"
            [ test "an agent: series id is an agent series" <|
                \_ ->
                    Data.isAgentSeries { baseRow | seriesId = Just "agent:GPTBot" }
                        |> Expect.equal True
            , test "a fixed series id is not an agent series" <|
                \_ ->
                    Data.isAgentSeries { baseRow | seriesId = Just "blanket" }
                        |> Expect.equal False
            , test "a print row (no series id) is not an agent series" <|
                \_ ->
                    Data.isAgentSeries baseRow
                        |> Expect.equal False
            , test "agentName strips the agent: prefix" <|
                \_ ->
                    Data.agentName { baseRow | seriesId = Just "agent:GPTBot" }
                        |> Expect.equal "GPTBot"
            ]
        , describe "seriesLabel"
            [ test "labels the fixed series ids" <|
                \_ ->
                    [ "blanket", "coverage", "effective", "unreadable" ]
                        |> List.map Data.seriesLabel
                        |> Expect.equal
                            [ "Blanket disallow (closed to every crawler)"
                            , "Coverage"
                            , "Effective (named or blanket)"
                            , "Unreadable robots.txt"
                            ]
            ]
        , describe "currentPeriod, latestPrint and findByPeriod"
            [ test "currentPeriod picks the lexicographically latest period" <|
                \_ ->
                    [ { baseRow | period = "2026-09-07" }, { baseRow | period = "2026-09-14" } ]
                        |> Data.currentPeriod
                        |> Expect.equal (Just "2026-09-14")
            , test "currentPeriod is Nothing for an empty list" <|
                \_ ->
                    Data.currentPeriod []
                        |> Expect.equal Nothing
            , test "latestPrint returns the row for the current period" <|
                \_ ->
                    [ { baseRow | period = "2026-09-07", value = "10" }, { baseRow | period = "2026-09-14", value = "20" } ]
                        |> Data.latestPrint
                        |> Maybe.map .value
                        |> Expect.equal (Just "20")
            , test "findByPeriod finds the matching row" <|
                \_ ->
                    [ { baseRow | period = "2026-09-07" }, { baseRow | period = "2026-09-14" } ]
                        |> Data.findByPeriod "2026-09-07"
                        |> Maybe.map .period
                        |> Expect.equal (Just "2026-09-07")
            ]
        , describe "latestByPeriod"
            [ test "keeps only the highest vintage for each period" <|
                \_ ->
                    [ { baseRow | period = "2026-09-14", vintage = "1", value = "old" }
                    , { baseRow | period = "2026-09-14", vintage = "2", value = "new" }
                    , { baseRow | period = "2026-09-07", vintage = "1", value = "only" }
                    ]
                        |> Data.latestByPeriod
                        |> List.map .value
                        |> List.sort
                        |> Expect.equal [ "new", "only" ]
            ]
        , describe "purposeLabel"
            [ test "labels known purpose categories" <|
                \_ ->
                    [ "training", "training-consent", "uncertain" ]
                        |> List.map Data.purposeLabel
                        |> Expect.equal [ "Training", "Training consent", "Uncertain" ]
            , test "falls back to the raw string for an unknown category" <|
                \_ ->
                    Data.purposeLabel "something-new"
                        |> Expect.equal "something-new"
            ]
        , describe "formatPercent"
            [ test "rounds to two decimal places and appends a percent sign" <|
                \_ ->
                    Data.formatPercent "23.4704"
                        |> Expect.equal "23.47%"
            , test "pads a whole coverage figure to two decimals" <|
                \_ ->
                    Data.formatPercent "99.7"
                        |> Expect.equal "99.70%"
            , test "falls back to the raw string when it does not parse as a number" <|
                \_ ->
                    Data.formatPercent "n/a"
                        |> Expect.equal "n/a"
            ]
        ]
