module DataTest exposing (suite)

import Data exposing (Download, Row)
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
    , "panelRows":
        [ { "domain": "google.com", "rank": 1, "outcome": "Fetched", "blocked": 0, "tracked": 45, "blanket": "Allowed" }
        , { "domain": "facebook.com", "rank": 3, "outcome": "Fetched", "blocked": 7, "tracked": 45, "blanket": "FullBlock" }
        , { "domain": "example.com", "rank": 9, "outcome": "Challenged", "blocked": 0, "tracked": 45, "blanket": "" }
        ]
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
    , "history":
        { "id": "agent-accessibility-history"
        , "title": "Three years of AI-crawler blocking"
        , "question": "When did the top websites start telling AI crawlers to stay out?"
        , "prints":
            [ { "period": "2023-01", "vintage": "1", "value": "1.2821", "denominator": "390", "coverage": "63.8298", "provisional": "false", "methodology_version": "agents=1;protego=0.6.2", "collector_version": "f5c2b39", "computed_at": "2026-09-17T15:56:22Z", "reason": "" }
            , { "period": "2026-08", "vintage": "1", "value": "27.8515", "denominator": "377", "coverage": "61.7021", "provisional": "false", "methodology_version": "agents=1;protego=0.6.2", "collector_version": "f5c2b39", "computed_at": "2026-09-17T15:56:22Z", "reason": "" }
            ]
        , "superseded": []
        , "series":
            [ { "period": "2026-08", "vintage": "1", "value": "1.1019", "denominator": "377", "coverage": "61.7021", "provisional": "false", "methodology_version": "agents=1;protego=0.6.2", "collector_version": "f5c2b39", "computed_at": "2026-09-17T15:56:22Z", "reason": "", "series_id": "change_since_previous" }
            ]
        , "panel":
            { "size": 611
            , "endpoints":
                [ { "tranco_list_id": "K2K4W", "date": "2023-02-01", "size": 1000 }
                , { "tranco_list_id": "N2P2W", "date": "2026-09-16", "size": 1000 }
                ]
            , "construction":
                { "rule": "domains present in the Tranco top-N at BOTH endpoints"
                , "churn": "389 of 1000 early entries absent at the later endpoint"
                , "known_bias": "members were prominent at both endpoints, so the panel is biased toward durably significant sites"
                , "not_comparable": "a different population from the live index panel, so levels are not comparable between the two indices"
                , "retained": 611
                }
            }
        , "crawls":
            [ { "crawl": "CC-MAIN-2023-06", "period": "2023-01", "name": "January/February 2023" }
            , { "crawl": "CC-MAIN-2026-34", "period": "2026-08", "name": "August 2026" }
            ]
        , "selection": "Roughly quarterly from January 2023 to August 2026."
        }
    , "crawler":
        { "userAgent": "TallyhouseIndexBot/1.0 (+https://allanderek.github.io/tallyhouse/about/crawler/)"
        , "token": "TallyhouseIndexBot"
        , "category": "Academic Research"
        , "purpose": "Fetches only /robots.txt, once a week, from a fixed published panel of domains, to measure how many sites disallow AI crawlers."
        , "contact": "https://github.com/allanderek/tallyhouse/issues"
        , "prefixes": [ "149.102.158.121/32" ]
        }
    , "methodology":
        { "composition": "A methodology version is the tracked agent set combined with the pinned parser."
        , "versions":
            [ { "version": "agents=1;protego=0.6.2"
              , "adopted": "2026-09-17"
              , "summary": "First published methodology."
              , "changed": "Initial agent set of 16 tokens."
              , "why": "The starting point."
              , "periods": []
              , "supersededPeriods": [ "2026-09-14" ]
              }
            , { "version": "agents=2;protego=0.6.2"
              , "adopted": "2026-09-19"
              , "summary": "Agent set expanded from 16 tokens to 45."
              , "changed": "Added 29 tokens."
              , "why": "An audit found the original set incomplete."
              , "periods": [ "2026-09-21" ]
              , "supersededPeriods": []
              }
            ]
        , "undocumented": []
        , "parameters":
            { "probePaths": [ "/", "/index.html", "/about", "/news/article-1", "/api/v1/data", "/images/photo.jpg" ]
            , "conclusiveOutcomes": [ "Fetched", "NoRobotsTxt" ]
            , "unreadableOutcomes": [ "Challenged", "ServerError" ]
            , "maxBodyBytes": 1024
            , "collectionWindowHours": 48
            , "provisionalCoverageThreshold": 91.5
            , "userAgent": "TallyhouseIndexBot/1.0 (+https://allanderek.github.io/tallyhouse/about/crawler/)"
            }
        }
    , "downloads":
        [ { "path": "data/prints.csv", "indexId": "", "label": "Headline ledger", "description": "Every headline figure ever published.", "bytes": 2532, "rows": 19 }
        ]
    }
    """


baseDownload : Download
baseDownload =
    { path = "data/prints.csv"
    , indexId = ""
    , label = "Headline ledger"
    , description = "Every headline figure ever published."
    , bytes = 2532
    , rows = 19
    }


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
            , test "panelRows decode every domain, including one with an empty blanket" <|
                \_ ->
                    Decode.decodeString Data.decodeFlags sampleJson
                        |> Result.map (\flags -> List.map .domain flags.panelRows)
                        |> Expect.equal (Ok [ "google.com", "facebook.com", "example.com" ])
            , test "a panelRow's numeric fields decode as integers, not strings" <|
                \_ ->
                    Decode.decodeString Data.decodeFlags sampleJson
                        |> Result.map (\flags -> List.map (\row -> ( row.rank, row.blocked, row.tracked )) flags.panelRows)
                        |> Expect.equal (Ok [ ( 1, 0, 45 ), ( 3, 7, 45 ), ( 9, 0, 45 ) ])
            , test "a panelRow with an unreadable robots.txt decodes blanket as the empty string, not \"Allowed\"" <|
                \_ ->
                    Decode.decodeString Data.decodeFlags sampleJson
                        |> Result.map (\flags -> List.filter (\row -> row.domain == "example.com") flags.panelRows |> List.map .blanket)
                        |> Expect.equal (Ok [ "" ])
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
            , test "the historical index decodes its own title, prints and panel" <|
                \_ ->
                    Decode.decodeString Data.decodeFlags sampleJson
                        |> Result.map
                            (\flags ->
                                ( flags.history.title
                                , List.map .period flags.history.prints
                                , flags.history.panel.size
                                )
                            )
                        |> Expect.equal (Ok ( "Three years of AI-crawler blocking", [ "2023-01", "2026-08" ], 611 ))
            , test "the historical panel's endpoints decode, tranco id and all" <|
                \_ ->
                    Decode.decodeString Data.decodeFlags sampleJson
                        |> Result.map (\flags -> List.map .trancoListId flags.history.panel.endpoints)
                        |> Expect.equal (Ok [ "K2K4W", "N2P2W" ])
            , test "the historical panel's retained count decodes as a number" <|
                \_ ->
                    Decode.decodeString Data.decodeFlags sampleJson
                        |> Result.map (\flags -> flags.history.panel.construction.retained)
                        |> Expect.equal (Ok 611)
            , test "the crawls decode, matching a period to a crawl name" <|
                \_ ->
                    Decode.decodeString Data.decodeFlags sampleJson
                        |> Result.map (\flags -> List.map .name flags.history.crawls)
                        |> Expect.equal (Ok [ "January/February 2023", "August 2026" ])
            , test "the downloads decode, path, label and sizes all" <|
                \_ ->
                    Decode.decodeString Data.decodeFlags sampleJson
                        |> Result.map .downloads
                        |> Expect.equal
                            (Ok
                                [ { path = "data/prints.csv"
                                  , indexId = ""
                                  , label = "Headline ledger"
                                  , description = "Every headline figure ever published."
                                  , bytes = 2532
                                  , rows = 19
                                  }
                                ]
                            )
            , test "the methodology's composition and parameters decode" <|
                \_ ->
                    Decode.decodeString Data.decodeFlags sampleJson
                        |> Result.map (\flags -> ( flags.methodology.composition, flags.methodology.parameters.collectionWindowHours, flags.methodology.parameters.provisionalCoverageThreshold ))
                        |> Expect.equal (Ok ( "A methodology version is the tracked agent set combined with the pinned parser.", 48, 91.5 ))
            , test "a methodology version decodes its periods and supersededPeriods" <|
                \_ ->
                    Decode.decodeString Data.decodeFlags sampleJson
                        |> Result.map (\flags -> List.map (\version -> ( version.version, version.periods, version.supersededPeriods )) flags.methodology.versions)
                        |> Expect.equal
                            (Ok
                                [ ( "agents=1;protego=0.6.2", [], [ "2026-09-14" ] )
                                , ( "agents=2;protego=0.6.2", [ "2026-09-21" ], [] )
                                ]
                            )
            , test "the methodology's probe paths decode in order" <|
                \_ ->
                    Decode.decodeString Data.decodeFlags sampleJson
                        |> Result.map (\flags -> flags.methodology.parameters.probePaths)
                        |> Expect.equal (Ok [ "/", "/index.html", "/about", "/news/article-1", "/api/v1/data", "/images/photo.jpg" ])
            , test "the crawler's identity decodes, user-agent and all" <|
                \_ ->
                    Decode.decodeString Data.decodeFlags sampleJson
                        |> Result.map (\flags -> flags.crawler)
                        |> Expect.equal
                            (Ok
                                { userAgent = "TallyhouseIndexBot/1.0 (+https://allanderek.github.io/tallyhouse/about/crawler/)"
                                , token = "TallyhouseIndexBot"
                                , category = "Academic Research"
                                , purpose = "Fetches only /robots.txt, once a week, from a fixed published panel of domains, to measure how many sites disallow AI crawlers."
                                , contact = "https://github.com/allanderek/tallyhouse/issues"
                                , prefixes = [ "149.102.158.121/32" ]
                                }
                            )
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
        , describe "formatFixed2"
            [ test "keeps the sign of a negative value smaller than one in magnitude" <|
                \_ ->
                    Data.formatFixed2 -0.2611
                        |> Expect.equal "-0.26"
            , test "keeps the sign of a negative value larger than one in magnitude" <|
                \_ ->
                    Data.formatFixed2 -1.2853
                        |> Expect.equal "-1.29"
            ]
        , describe "biggestMove"
            [ test "picks the change_since_previous row with the greatest value" <|
                \_ ->
                    [ { baseRow | period = "2023-03", value = "0.5182", seriesId = Just "change_since_previous" }
                    , { baseRow | period = "2023-09", value = "13.6483", seriesId = Just "change_since_previous" }
                    , { baseRow | period = "2025-04", value = "-1.2853", seriesId = Just "change_since_previous" }
                    , { baseRow | period = "2023-09", value = "999", seriesId = Just "effective" }
                    ]
                        |> Data.biggestMove
                        |> Maybe.map .period
                        |> Expect.equal (Just "2023-09")
            , test "is Nothing for an empty list" <|
                \_ ->
                    Data.biggestMove []
                        |> Expect.equal Nothing
            , test "is Nothing when there are no change_since_previous rows" <|
                \_ ->
                    [ { baseRow | seriesId = Just "effective" }, { baseRow | seriesId = Just "blanket" } ]
                        |> Data.biggestMove
                        |> Expect.equal Nothing
            ]
        , describe "agentHistory"
            [ test "returns only the named token's rows, ordered by period" <|
                \_ ->
                    [ { baseRow | period = "2023-09", value = "14.0", seriesId = Just "agent:GPTBot" }
                    , { baseRow | period = "2023-01", value = "0.0", seriesId = Just "agent:GPTBot" }
                    , { baseRow | period = "2023-01", value = "5.0", seriesId = Just "agent:ClaudeBot" }
                    , { baseRow | period = "2023-01", value = "1.1", seriesId = Just "coverage" }
                    ]
                        |> Data.agentHistory "GPTBot"
                        |> List.map .period
                        |> Expect.equal [ "2023-01", "2023-09" ]
            , test "an unknown token has no history" <|
                \_ ->
                    [ { baseRow | seriesId = Just "agent:GPTBot" } ]
                        |> Data.agentHistory "NoSuchBot"
                        |> Expect.equal []
            ]
        , describe "firstBlockedPeriod"
            [ test "finds the earliest period with a non-zero value" <|
                \_ ->
                    [ { baseRow | period = "2023-01", value = "0.0" }
                    , { baseRow | period = "2023-09", value = "14.0" }
                    , { baseRow | period = "2024-02", value = "16.9" }
                    ]
                        |> Data.firstBlockedPeriod
                        |> Expect.equal (Just "2023-09")
            , test "is Nothing when every value is zero" <|
                \_ ->
                    [ { baseRow | period = "2023-01", value = "0.0" }
                    , { baseRow | period = "2023-09", value = "0.0" }
                    ]
                        |> Data.firstBlockedPeriod
                        |> Expect.equal Nothing
            , test "is Nothing for an empty list" <|
                \_ ->
                    Data.firstBlockedPeriod []
                        |> Expect.equal Nothing
            , test "is not fooled by a later zero after a non-zero reading" <|
                \_ ->
                    [ { baseRow | period = "2023-01", value = "0.0" }
                    , { baseRow | period = "2023-09", value = "14.0" }
                    , { baseRow | period = "2024-02", value = "0.0" }
                    ]
                        |> Data.firstBlockedPeriod
                        |> Expect.equal (Just "2023-09")
            ]
        , describe "earliestPrint"
            [ test "picks the earliest period, not merely the list head" <|
                \_ ->
                    [ { baseRow | period = "2026-08" }, { baseRow | period = "2023-01" }, { baseRow | period = "2024-05" } ]
                        |> Data.earliestPrint
                        |> Maybe.map .period
                        |> Expect.equal (Just "2023-01")
            , test "is Nothing for an empty list" <|
                \_ ->
                    Data.earliestPrint []
                        |> Expect.equal Nothing
            ]
        , describe "humanBytes"
            [ test "a small size is a bare byte count" <|
                \_ ->
                    Data.humanBytes 512
                        |> Expect.equal "512 B"
            , test "just under 1 KB stays a bare byte count" <|
                \_ ->
                    Data.humanBytes 1023
                        |> Expect.equal "1023 B"
            , test "just over 1 KB switches to KB with one decimal" <|
                \_ ->
                    Data.humanBytes 1024
                        |> Expect.equal "1.0 KB"
            , test "a typical KB-sized download" <|
                \_ ->
                    Data.humanBytes 2532
                        |> Expect.equal "2.5 KB"
            , test "just under 1 MB stays in KB" <|
                \_ ->
                    Data.humanBytes 1048575
                        |> Expect.equal "1024.0 KB"
            , test "just over 1 MB switches to MB with one decimal" <|
                \_ ->
                    Data.humanBytes 1048576
                        |> Expect.equal "1.0 MB"
            , test "a typical MB-sized download" <|
                \_ ->
                    Data.humanBytes 2203648
                        |> Expect.equal "2.1 MB"
            ]
        , describe "downloadsFor"
            [ test "keeps a shared download (empty indexId)" <|
                \_ ->
                    [ { baseDownload | indexId = "" } ]
                        |> Data.downloadsFor "agent-accessibility"
                        |> List.length
                        |> Expect.equal 1
            , test "keeps a download owned by the given index" <|
                \_ ->
                    [ { baseDownload | path = "data/panel-2026-09-28.csv", indexId = "agent-accessibility" } ]
                        |> Data.downloadsFor "agent-accessibility"
                        |> List.map .path
                        |> Expect.equal [ "data/panel-2026-09-28.csv" ]
            , test "drops a download owned by a different index" <|
                \_ ->
                    [ { baseDownload | path = "data/panel-historical.csv", indexId = "agent-accessibility-history" } ]
                        |> Data.downloadsFor "agent-accessibility"
                        |> Expect.equal []
            , test "preserves input order across shared and owned entries" <|
                \_ ->
                    [ { baseDownload | path = "data/prints.csv", indexId = "" }
                    , { baseDownload | path = "data/panel-2026-09-28.csv", indexId = "agent-accessibility" }
                    , { baseDownload | path = "data/panel-historical.csv", indexId = "agent-accessibility-history" }
                    , { baseDownload | path = "data/series.csv", indexId = "" }
                    ]
                        |> Data.downloadsFor "agent-accessibility"
                        |> List.map .path
                        |> Expect.equal [ "data/prints.csv", "data/panel-2026-09-28.csv", "data/series.csv" ]
            , test "returns [] from []" <|
                \_ ->
                    Data.downloadsFor "agent-accessibility" []
                        |> Expect.equal []
            ]
        ]
