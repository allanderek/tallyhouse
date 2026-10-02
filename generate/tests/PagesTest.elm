module PagesTest exposing (suite)

import Data exposing (Agent, Download, Flags, History, Operator, Panel, Row, Stances)
import Dict
import Expect
import Json.Decode as Decode
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


baseStances : Stances
baseStances =
    { fullBlock = 10, partialBlock = 2, allowed = 3, unmentioned = 5 }


gptBot : Agent
gptBot =
    { token = "GPTBot"
    , slug = "gptbot"
    , operator = "OpenAI"
    , purpose = "training"
    , description = "Collects web content to train OpenAI generative models."
    , seriesId = "agent:GPTBot"
    , stances = baseStances
    }


oaiSearchBot : Agent
oaiSearchBot =
    { token = "OAI-SearchBot"
    , slug = "oai-searchbot"
    , operator = "OpenAI"
    , purpose = "search"
    , description = "Indexes pages for ChatGPT search answers."
    , seriesId = "agent:OAI-SearchBot"
    , stances = baseStances
    }


googleExtended : Agent
googleExtended =
    { token = "Google-Extended"
    , slug = "google-extended"
    , operator = "Google"
    , purpose = "training-consent"
    , description = "Not a crawler. Withholds permission to train on content Googlebot already fetched."
    , seriesId = "agent:Google-Extended"
    , stances = baseStances
    }


claudeWeb : Agent
claudeWeb =
    { token = "Claude-Web"
    , slug = "claude-web"
    , operator = "Anthropic"
    , purpose = "uncertain"
    , description = "Named in many robots.txt files but observed traffic appears minimal."
    , seriesId = "agent:Claude-Web"
    , stances = baseStances
    }


openAiOperator : Operator
openAiOperator =
    { name = "OpenAI"
    , description = "Operates separately-named tokens for separate jobs."
    , tokens = [ "GPTBot", "OAI-SearchBot" ]
    , divergentCount = 3
    , divergentExamples =
        [ { domain = "example.com"
          , stances = Dict.fromList [ ( "GPTBot", "FullBlock" ), ( "OAI-SearchBot", "Unmentioned" ) ]
          }
        ]
    }


googleOperator : Operator
googleOperator =
    { name = "Google"
    , description = "Only Google-Extended is a consent signal."
    , tokens = [ "Google-Extended" ]
    , divergentCount = 0
    , divergentExamples = []
    }


anthropicOperator : Operator
anthropicOperator =
    { name = "Anthropic"
    , description = "Tracks Anthropic's crawlers and consent tokens."
    , tokens = [ "Claude-Web" ]
    , divergentCount = 0
    , divergentExamples = []
    }


basePurposes : Dict.Dict String String
basePurposes =
    Dict.fromList
        [ ( "training", "Bulk crawling to build model training data." )
        , ( "search", "Indexes pages so an answer engine can retrieve and cite them." )
        , ( "training-consent", "Not a crawler at all. A signal withholding permission to train on content already fetched by a conventional crawler." )
        , ( "uncertain", "Purpose not established. The token is tracked without claiming to know what it is for." )
        ]


historyBaseRow : Row
historyBaseRow =
    { baseRow | period = "2023-01", value = "1.2800", denominator = "390", coverage = "63.8000" }


historyEarliestPrint : Row
historyEarliestPrint =
    historyBaseRow


historyMidPrint : Row
historyMidPrint =
    { historyBaseRow | period = "2023-09", value = "15.9300", denominator = "408", coverage = "66.7000" }


historyLatestPrint : Row
historyLatestPrint =
    { historyBaseRow | period = "2026-08", value = "27.8500", denominator = "377", coverage = "61.7000" }


baseHistory : History
baseHistory =
    { id = "agent-accessibility-history"
    , title = "Three years of AI-crawler blocking"
    , question = "When did the top websites start telling AI crawlers to stay out?"
    , prints = [ historyEarliestPrint, historyMidPrint, historyLatestPrint ]
    , superseded = []
    , series =
        [ { historyMidPrint | value = "13.6500", seriesId = Just "change_since_previous" }
        , { historyLatestPrint | value = "1.1000", seriesId = Just "change_since_previous" }
        , { historyEarliestPrint | value = "63.8000", seriesId = Just "coverage" }
        , { historyMidPrint | value = "66.7000", seriesId = Just "coverage" }
        , { historyLatestPrint | value = "61.7000", seriesId = Just "coverage" }
        , { historyLatestPrint | value = "29.0000", seriesId = Just "effective" }
        , { historyEarliestPrint | value = "0.0000", seriesId = Just "agent:GPTBot" }
        , { historyMidPrint | value = "14.0000", seriesId = Just "agent:GPTBot" }
        , { historyLatestPrint | value = "19.1000", seriesId = Just "agent:GPTBot" }
        ]
    , panel =
        { size = 611
        , endpoints =
            [ { trancoListId = "K2K4W", date = "2023-02-01", size = 1000 }
            , { trancoListId = "N2P2W", date = "2026-09-16", size = 1000 }
            ]
        , construction =
            { rule = "domains present in the Tranco top-N at BOTH endpoints"
            , churn = "389 of 1000 early entries absent at the later endpoint"
            , knownBias = "members were prominent at both endpoints, so the panel is biased toward durably significant sites"
            , notComparable = "a different population from the live index panel, so levels are not comparable between the two indices"
            , retained = 611
            }
        }
    , crawls =
        [ { crawl = "CC-MAIN-2023-06", period = "2023-01", name = "January/February 2023" }
        , { crawl = "CC-MAIN-2023-40", period = "2023-09", name = "September/October 2023" }
        , { crawl = "CC-MAIN-2026-34", period = "2026-08", name = "August 2026" }
        ]
    , selection = "Roughly quarterly from January 2023 to August 2026. Test fixture selection text."
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
        , { baseRow | value = "8.1234", seriesId = Just "agent:OAI-SearchBot" }
        , { baseRow | value = "12.5000", seriesId = Just "agent:Google-Extended" }
        , { baseRow | value = "7.3000", seriesId = Just "agent:Claude-Web" }
        ]
    , panel = basePanel
    , agents =
        Dict.fromList
            [ ( "GPTBot", gptBot )
            , ( "OAI-SearchBot", oaiSearchBot )
            , ( "Google-Extended", googleExtended )
            , ( "Claude-Web", claudeWeb )
            ]
    , operators =
        Dict.fromList
            [ ( "OpenAI", openAiOperator )
            , ( "Google", googleOperator )
            , ( "Anthropic", anthropicOperator )
            ]
    , purposes = basePurposes
    , history = baseHistory
    , crawler = baseCrawler
    , methodology = baseMethodology
    , downloads = baseDownloads
    }


{-| Deliberately different from the real pipeline's own constants (72 hours,
97.0%, 512 KB): a test asserting these fixture values appear on the
rendered page is the only way to prove they were interpolated from
`flags.methodology.parameters` rather than typed into the page as literals.
-}
baseMethodologyParameters : Data.MethodologyParameters
baseMethodologyParameters =
    { probePaths = [ "/", "/index.html", "/about", "/news/article-1", "/api/v1/data", "/images/photo.jpg" ]
    , conclusiveOutcomes = [ "Fetched", "NoRobotsTxt" ]
    , unreadableOutcomes = [ "Challenged", "ServerError" ]
    , maxBodyBytes = 1024
    , collectionWindowHours = 48
    , provisionalCoverageThreshold = 91.5
    , userAgent = "TallyhouseIndexBot/1.0 (+https://allanderek.github.io/tallyhouse/about/crawler/)"
    }


firstMethodologyVersion : Data.MethodologyVersion
firstMethodologyVersion =
    { version = "agents=1;protego=0.6.2"
    , adopted = "2026-09-17"
    , summary = "First published methodology."
    , changed = "Initial agent set of 16 tokens, classified with protego 0.6.2."
    , why = "The starting point, published so later changes have something to be measured against."
    , periods = []
    , supersededPeriods = [ "2026-09-14" ]
    }


secondMethodologyVersion : Data.MethodologyVersion
secondMethodologyVersion =
    { version = "agents=2;protego=0.6.2"
    , adopted = "2026-09-19"
    , summary = "Agent set expanded from 16 tokens to 45."
    , changed = "Added 29 tokens that were live and widely named but untracked."
    , why = "An audit found the original set incomplete enough to understate the headline."
    , periods = [ "2026-09-21" ]
    , supersededPeriods = []
    }


baseMethodology : Data.Methodology
baseMethodology =
    { composition = "A methodology version is the tracked agent set combined with the pinned parser."
    , versions = [ firstMethodologyVersion, secondMethodologyVersion ]
    , undocumented = []
    , parameters = baseMethodologyParameters
    }


baseCrawler : Data.Crawler
baseCrawler =
    { userAgent = "TallyhouseIndexBot/1.0 (+https://allanderek.github.io/tallyhouse/about/crawler/)"
    , token = "TallyhouseIndexBot"
    , category = "Academic Research"
    , purpose = "Fetches only /robots.txt, once a week, from a fixed published panel of domains, to measure how many sites disallow AI crawlers."
    , contact = "https://github.com/allanderek/tallyhouse/issues"
    , prefixes = [ "149.102.158.121/32" ]
    }


printsDownload : Download
printsDownload =
    { path = "data/prints.csv"
    , indexId = ""
    , label = "Headline ledger"
    , description = "Every headline figure ever published, for both indices."
    , bytes = 2532
    , rows = 19
    }


seriesDownload : Download
seriesDownload =
    { path = "data/series.csv"
    , indexId = ""
    , label = "Series ledger"
    , description = "Every sub-series: per-crawler rates, effective and blanket blocking, coverage."
    , bytes = 2203648
    , rows = 4521
    }


liveOnlyDownload : Download
liveOnlyDownload =
    { path = "data/panel-2026-09-28.csv"
    , indexId = "agent-accessibility"
    , label = "Panel, 2026-09-28"
    , description = "The domains measured in this period, with their Tranco rank."
    , bytes = 15000
    , rows = 1000
    }


historyOnlyDownload : Download
historyOnlyDownload =
    { path = "data/panel-historical.csv"
    , indexId = "agent-accessibility-history"
    , label = "Balanced panel"
    , description = "The domains measured by the historical index."
    , bytes = 9000
    , rows = 611
    }


baseDownloads : List Download
baseDownloads =
    [ printsDownload, seriesDownload, liveOnlyDownload, historyOnlyDownload ]


agentContent : Flags -> String -> String
agentContent flags slug =
    Pages.pages flags
        |> List.filter (\page -> page.path == String.concat [ "agent-accessibility/agents/", slug, "/index.html" ])
        |> List.map .content
        |> String.concat


agentsIndexContent : Flags -> String
agentsIndexContent flags =
    Pages.pages flags
        |> List.filter (\page -> page.path == "agent-accessibility/agents/index.html")
        |> List.map .content
        |> String.concat


agentAccessibilityContent : Flags -> String
agentAccessibilityContent flags =
    Pages.pages flags
        |> List.filter (\page -> page.path == "agent-accessibility/index.html")
        |> List.map .content
        |> String.concat


homeContent : Flags -> String
homeContent flags =
    Pages.pages flags
        |> List.filter (\page -> page.path == "index.html")
        |> List.map .content
        |> String.concat


historyContent : Flags -> String
historyContent flags =
    Pages.pages flags
        |> List.filter (\page -> page.path == "agent-accessibility-history/index.html")
        |> List.map .content
        |> String.concat


aboutContent : Flags -> String
aboutContent flags =
    Pages.pages flags
        |> List.filter (\page -> page.path == "about/index.html")
        |> List.map .content
        |> String.concat


methodologyContent : Flags -> String
methodologyContent flags =
    Pages.pages flags
        |> List.filter (\page -> page.path == "agent-accessibility/methodology/index.html")
        |> List.map .content
        |> String.concat


crawlerContent : Flags -> String
crawlerContent flags =
    Pages.pages flags
        |> List.filter (\page -> page.path == "about/crawler/index.html")
        |> List.map .content
        |> String.concat


crawlerIpsContent : Flags -> String
crawlerIpsContent flags =
    Pages.pages flags
        |> List.filter (\page -> page.path == "about/crawler/ips.json")
        |> List.map .content
        |> String.concat


releaseContent : Flags -> String -> String -> String
releaseContent flags basePath period =
    Pages.pages flags
        |> List.filter (\page -> page.path == String.concat [ basePath, "/releases/", period, "/index.html" ])
        |> List.map .content
        |> String.concat


releasesIndexContent : Flags -> String -> String
releasesIndexContent flags basePath =
    Pages.pages flags
        |> List.filter (\page -> page.path == String.concat [ basePath, "/releases/index.html" ])
        |> List.map .content
        |> String.concat


suite : Test
suite =
    describe "Pages"
        [ describe "emitted paths"
            [ test "emits the expected relative paths, including one page per agent" <|
                \_ ->
                    Pages.pages baseFlags
                        |> List.map .path
                        |> Expect.equal
                            [ "index.html"
                            , "agent-accessibility/index.html"
                            , "agent-accessibility-history/index.html"
                            , "agent-accessibility/releases/index.html"
                            , "agent-accessibility-history/releases/index.html"
                            , "agent-accessibility/agents/index.html"
                            , "agent-accessibility/methodology/index.html"
                            , "agent-accessibility/agents/claude-web/index.html"
                            , "agent-accessibility/agents/gptbot/index.html"
                            , "agent-accessibility/agents/google-extended/index.html"
                            , "agent-accessibility/agents/oai-searchbot/index.html"
                            , "agent-accessibility/releases/2026-09-14/index.html"
                            , "agent-accessibility-history/releases/2023-01/index.html"
                            , "agent-accessibility-history/releases/2023-09/index.html"
                            , "agent-accessibility-history/releases/2026-08/index.html"
                            , "about/index.html"
                            , "about/crawler/index.html"
                            , "about/crawler/ips.json"
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
            , test "a series table heads its value column 'Value', since the row's series names the quantity" <|
                \_ ->
                    agentAccessibilityContent baseFlags
                        |> String.contains "<th>Series</th><th>Value</th>"
                        |> Expect.equal True
            ]
        , describe "the live index's prints table"
            [ test "heads its value column 'Targeted', not the ledger field name 'Value'" <|
                \_ ->
                    agentAccessibilityContent baseFlags
                        |> String.contains "<th>Period</th><th>Targeted</th><th>Coverage</th><th>Status</th>"
                        |> Expect.equal True
            ]
        , describe "the panel's known bias"
            [ test "appears on the index page" <|
                \_ ->
                    agentAccessibilityContent baseFlags
                        |> String.contains basePanel.qualification.knownBias
                        |> Expect.equal True
            , test "the bias callout's known-bias sentence ends in a full stop" <|
                \_ ->
                    agentAccessibilityContent baseFlags
                        |> String.contains (String.concat [ basePanel.qualification.knownBias, "." ])
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
            , test "the about page's known-bias sentence ends in a full stop" <|
                \_ ->
                    aboutContent baseFlags
                        |> String.contains (String.concat [ basePanel.qualification.knownBias, "." ])
                        |> Expect.equal True
            ]
        , describe "related work on the about page"
            [ test "links to the Agentic Web Index" <|
                \_ ->
                    aboutContent baseFlags
                        |> String.contains "<a href=\"https://knownagents.com/insights\">"
                        |> Expect.equal True
            , test "quotes Known Agents' sampling caveat" <|
                \_ ->
                    aboutContent baseFlags
                        |> String.contains "Participating websites are not a random sample, and the qualifying set changes over time, so results show observed directional trends rather than a census of global web traffic."
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
        , describe "the agent directory"
            [ test "lists every tracked agent, grouped by operator" <|
                \_ ->
                    let
                        content =
                            agentsIndexContent baseFlags
                    in
                    Expect.all
                        [ String.contains "OpenAI" >> Expect.equal True
                        , String.contains "Google" >> Expect.equal True
                        , String.contains "Anthropic" >> Expect.equal True
                        , String.contains "GPTBot" >> Expect.equal True
                        , String.contains "OAI-SearchBot" >> Expect.equal True
                        , String.contains "Google-Extended" >> Expect.equal True
                        , String.contains "Claude-Web" >> Expect.equal True
                        ]
                        content
            , test "links each agent to its own page, one level down from the directory" <|
                \_ ->
                    agentsIndexContent baseFlags
                        |> String.contains "href=\"gptbot/index.html\""
                        |> Expect.equal True
            , test "shows a multi-token operator's divergent domain count" <|
                \_ ->
                    agentsIndexContent baseFlags
                        |> String.contains "3 domains in the panel set OpenAI&#39;s tokens differently"
                        |> Expect.equal True
            ]
        , describe "a per-agent page"
            [ test "carries the token, operator, purpose and description" <|
                \_ ->
                    let
                        content =
                            agentContent baseFlags "gptbot"
                    in
                    Expect.all
                        [ String.contains "GPTBot" >> Expect.equal True
                        , String.contains "OpenAI" >> Expect.equal True
                        , String.contains "Training" >> Expect.equal True
                        , String.contains gptBot.description >> Expect.equal True
                        , String.contains "Bulk crawling to build model training data." >> Expect.equal True
                        ]
                        content
            , test "shows the published rate for the current period" <|
                \_ ->
                    agentContent baseFlags "gptbot"
                        |> String.contains "16.35%"
                        |> Expect.equal True
            , test "explains all four stances, including that unmentioned is not consent" <|
                \_ ->
                    let
                        content =
                            agentContent baseFlags "gptbot"
                    in
                    Expect.all
                        [ String.contains "FullBlock" >> Expect.equal True
                        , String.contains "PartialBlock" >> Expect.equal True
                        , String.contains "Allowed" >> Expect.equal True
                        , String.contains "Unmentioned" >> Expect.equal True
                        , String.contains "This is not consent" >> Expect.equal True
                        ]
                        content
            , test "shows sibling tokens from the same operator, with their own rates" <|
                \_ ->
                    let
                        content =
                            agentContent baseFlags "gptbot"
                    in
                    Expect.all
                        [ String.contains "OAI-SearchBot" >> Expect.equal True
                        , String.contains "8.12%" >> Expect.equal True
                        , String.contains "../oai-searchbot/index.html" >> Expect.equal True
                        ]
                        content
            , test "a single-token operator's page has no siblings section" <|
                \_ ->
                    agentContent baseFlags "google-extended"
                        |> String.contains "other tokens"
                        |> Expect.equal False
            , test "renders the divergence table and states the true total when the sample is capped" <|
                \_ ->
                    let
                        content =
                            agentContent baseFlags "gptbot"
                    in
                    Expect.all
                        [ String.contains "example.com" >> Expect.equal True
                        , String.contains "3 domains in the panel treat OpenAI&#39;s tokens differently" >> Expect.equal True
                        , String.contains "The first 1 are shown below" >> Expect.equal True
                        ]
                        content
            , test "a single-token operator's page has no divergence table" <|
                \_ ->
                    agentContent baseFlags "google-extended"
                        |> String.contains "treat these tokens differently"
                        |> Expect.equal False
            , test "a training-consent token states plainly that it is not a crawler" <|
                \_ ->
                    let
                        content =
                            agentContent baseFlags "google-extended"
                    in
                    Expect.all
                        [ String.contains "Not a crawler" >> Expect.equal True
                        , String.contains "does not fetch pages" >> Expect.equal True
                        ]
                        content
            , test "an uncertain-purpose token says its purpose is not established" <|
                \_ ->
                    agentContent baseFlags "claude-web"
                        |> String.contains "not because its purpose is known with confidence"
                        |> Expect.equal True
            , test "links back to the directory and the index page" <|
                \_ ->
                    let
                        content =
                            agentContent baseFlags "gptbot"
                    in
                    Expect.all
                        [ String.contains "../../agents/index.html" >> Expect.equal True
                        , String.contains "../../index.html" >> Expect.equal True
                        ]
                        content
            , test "carries a three-year section with a value from the historical fixture" <|
                \_ ->
                    agentContent baseFlags "gptbot"
                        |> String.contains "19.10%"
                        |> Expect.equal True
            , test "names the period the token was first blocked in" <|
                \_ ->
                    agentContent baseFlags "gptbot"
                        |> String.contains "2023-09"
                        |> Expect.equal True
            , test "carries the not-comparable caution, naming the historical panel size" <|
                \_ ->
                    let
                        content =
                            agentContent baseFlags "gptbot"
                    in
                    Expect.all
                        [ String.contains baseHistory.panel.construction.notComparable >> Expect.equal True
                        , String.contains "611" >> Expect.equal True
                        ]
                        content
            , test "a token with no historical rows omits the three-year section entirely" <|
                \_ ->
                    let
                        content =
                            agentContent baseFlags "claude-web"
                    in
                    Expect.all
                        [ String.contains "three-year history" >> Expect.equal False
                        , String.contains baseHistory.panel.construction.notComparable >> Expect.equal False
                        ]
                        content
            ]
        , describe "the crawler page"
            [ test "is present at about/crawler/index.html" <|
                \_ ->
                    Pages.pages baseFlags
                        |> List.map .path
                        |> List.member "about/crawler/index.html"
                        |> Expect.equal True
            , test "names the user-agent token" <|
                \_ ->
                    crawlerContent baseFlags
                        |> String.contains "TallyhouseIndexBot"
                        |> Expect.equal True
            , test "states that only robots.txt is fetched" <|
                \_ ->
                    crawlerContent baseFlags
                        |> String.contains "It requests exactly one file from your site"
                        |> Expect.equal True
            , test "links home two directories up" <|
                \_ ->
                    crawlerContent baseFlags
                        |> String.contains "../../index.html"
                        |> Expect.equal True
            , test "has no root-relative links" <|
                \_ ->
                    crawlerContent baseFlags
                        |> String.contains "href=\"/index.html\""
                        |> Expect.equal False
            , test "shows the user-agent read from flags, not a hardcoded string" <|
                \_ ->
                    let
                        flags =
                            { baseFlags | crawler = { baseCrawler | userAgent = "DistinctiveTestBot/9.9 (+https://example.test/)" } }
                    in
                    crawlerContent flags
                        |> String.contains "DistinctiveTestBot/9.9 (+https://example.test/)"
                        |> Expect.equal True
            , test "lists the egress prefix from the fixture" <|
                \_ ->
                    crawlerContent baseFlags
                        |> String.contains "149.102.158.121/32"
                        |> Expect.equal True
            , test "links to the machine-readable ips.json" <|
                \_ ->
                    crawlerContent baseFlags
                        |> String.contains "href=\"ips.json\""
                        |> Expect.equal True
            , test "with no published prefixes, says no list is published and links to nothing" <|
                \_ ->
                    let
                        flags =
                            { baseFlags | crawler = { baseCrawler | prefixes = [] } }

                        content =
                            crawlerContent flags
                    in
                    Expect.all
                        [ String.contains "No address list is currently published." >> Expect.equal True
                        , String.contains "href=\"ips.json\"" >> Expect.equal False
                        ]
                        content
            ]
        , describe "the crawler ips.json page"
            [ test "is present at about/crawler/ips.json" <|
                \_ ->
                    Pages.pages baseFlags
                        |> List.map .path
                        |> List.member "about/crawler/ips.json"
                        |> Expect.equal True
            , test "parses as JSON carrying the fixture's IPv4 prefix" <|
                \_ ->
                    crawlerIpsContent baseFlags
                        |> Decode.decodeString (Decode.field "prefixes" (Decode.list (Decode.field "ipv4Prefix" Decode.string)))
                        |> Expect.equal (Ok [ "149.102.158.121/32" ])
            , test "emits an IPv6 prefix under ipv6Prefix, not ipv4Prefix" <|
                \_ ->
                    let
                        flags =
                            { baseFlags | crawler = { baseCrawler | prefixes = [ "2001:db8::1/128" ] } }
                    in
                    crawlerIpsContent flags
                        |> Decode.decodeString (Decode.field "prefixes" (Decode.list (Decode.field "ipv6Prefix" Decode.string)))
                        |> Expect.equal (Ok [ "2001:db8::1/128" ])
            , test "with no published prefixes, still renders valid JSON with an empty prefixes array" <|
                \_ ->
                    let
                        flags =
                            { baseFlags | crawler = { baseCrawler | prefixes = [] } }
                    in
                    crawlerIpsContent flags
                        |> Decode.decodeString (Decode.field "prefixes" (Decode.list Decode.value))
                        |> Expect.equal (Ok [])
            ]
        , describe "the home page's lead prose"
            [ test "carries the historical series' latest value, computed rather than hardcoded" <|
                \_ ->
                    homeContent baseFlags
                        |> String.contains "27.85%"
                        |> Expect.equal True
            , test "names the biggest-move period from the fixture" <|
                \_ ->
                    homeContent baseFlags
                        |> String.contains "2023-09"
                        |> Expect.equal True
            , test "carries the size of the biggest move, in points" <|
                \_ ->
                    homeContent baseFlags
                        |> String.contains "13.65"
                        |> Expect.equal True
            , test "carries the earliest print's period and value" <|
                \_ ->
                    let
                        content =
                            homeContent baseFlags
                    in
                    Expect.all
                        [ String.contains "2023-01" >> Expect.equal True
                        , String.contains "1.28%" >> Expect.equal True
                        ]
                        content
            , test "links to both the weekly and historical indices" <|
                \_ ->
                    let
                        content =
                            homeContent baseFlags
                    in
                    Expect.all
                        [ String.contains "href=\"agent-accessibility/index.html\"" >> Expect.equal True
                        , String.contains "href=\"agent-accessibility-history/index.html\"" >> Expect.equal True
                        ]
                        content
            , test "carries the live index's own, different headline value" <|
                \_ ->
                    homeContent baseFlags
                        |> String.contains "23.47%"
                        |> Expect.equal True
            , test "cautions that the two panels are not comparable" <|
                \_ ->
                    homeContent baseFlags
                        |> String.contains baseHistory.panel.construction.notComparable
                        |> Expect.equal True
            ]
        , describe "the historical index page"
            [ test "exists at agent-accessibility-history/index.html" <|
                \_ ->
                    Pages.pages baseFlags
                        |> List.map .path
                        |> List.member "agent-accessibility-history/index.html"
                        |> Expect.equal True
            , test "lists every fixture period" <|
                \_ ->
                    let
                        content =
                            historyContent baseFlags
                    in
                    Expect.all
                        [ String.contains "2023-01" >> Expect.equal True
                        , String.contains "2023-09" >> Expect.equal True
                        , String.contains "2026-08" >> Expect.equal True
                        ]
                        content
            , test "shows the latest period's own headline value, not the live index's" <|
                \_ ->
                    historyContent baseFlags
                        |> String.contains "27.85%"
                        |> Expect.equal True
            , test "shows the coverage range computed from the fixture's coverage rows" <|
                \_ ->
                    let
                        content =
                            historyContent baseFlags
                    in
                    Expect.all
                        [ String.contains "61.70%" >> Expect.equal True
                        , String.contains "66.70%" >> Expect.equal True
                        ]
                        content
            , test "links both Tranco endpoint list ids" <|
                \_ ->
                    let
                        content =
                            historyContent baseFlags
                    in
                    Expect.all
                        [ String.contains "<a href=\"https://tranco-list.eu/list/K2K4W\">" >> Expect.equal True
                        , String.contains "<a href=\"https://tranco-list.eu/list/N2P2W\">" >> Expect.equal True
                        ]
                        content
            , test "names every crawl in the selection list" <|
                \_ ->
                    let
                        content =
                            historyContent baseFlags
                    in
                    Expect.all
                        [ String.contains "CC-MAIN-2023-06" >> Expect.equal True
                        , String.contains "September/October 2023" >> Expect.equal True
                        ]
                        content
            , test "labels the table's value and denominator columns for a reader, not a ledger" <|
                \_ ->
                    let
                        content =
                            historyContent baseFlags
                    in
                    Expect.all
                        [ String.contains "<th>Targeted</th>" >> Expect.equal True
                        , String.contains "<th>Conclusive domains</th>" >> Expect.equal True
                        , String.contains "<th>Value</th>" >> Expect.equal False
                        , String.contains "<th>Denominator</th>" >> Expect.equal False
                        ]
                        content
            , test "signs a positive change with an explicit +" <|
                \_ ->
                    let
                        content =
                            historyContent baseFlags
                    in
                    Expect.all
                        [ String.contains "+13.65" >> Expect.equal True
                        , String.contains "+1.10" >> Expect.equal True
                        ]
                        content
            , test "leaves the first period's change cell empty" <|
                \_ ->
                    historyContent baseFlags
                        |> String.contains "<td>2023-01</td><td>January/February 2023</td><td>1.28%</td><td></td><td>390</td><td>63.80%</td>"
                        |> Expect.equal True
            ]
        , describe "the Downloads section"
            [ test "the live index links the prints download one directory up, with its label and size" <|
                \_ ->
                    let
                        content =
                            agentAccessibilityContent baseFlags
                    in
                    Expect.all
                        [ String.contains "<h2>Downloads</h2>" >> Expect.equal True
                        , String.contains "href=\"../data/prints.csv\"" >> Expect.equal True
                        , String.contains "Headline ledger" >> Expect.equal True
                        , String.contains "2.5 KB" >> Expect.equal True
                        ]
                        content
            , test "the historical index also links downloads one directory up" <|
                \_ ->
                    let
                        content =
                            historyContent baseFlags
                    in
                    Expect.all
                        [ String.contains "<h2>Downloads</h2>" >> Expect.equal True
                        , String.contains "href=\"../data/prints.csv\"" >> Expect.equal True
                        , String.contains "href=\"../data/series.csv\"" >> Expect.equal True
                        , String.contains "2.1 MB" >> Expect.equal True
                        ]
                        content
            , test "the live index links the shared downloads and its own, but not the historical index's" <|
                \_ ->
                    let
                        content =
                            agentAccessibilityContent baseFlags
                    in
                    Expect.all
                        [ String.contains "href=\"../data/prints.csv\"" >> Expect.equal True
                        , String.contains "href=\"../data/series.csv\"" >> Expect.equal True
                        , String.contains "href=\"../data/panel-2026-09-28.csv\"" >> Expect.equal True
                        , String.contains "href=\"../data/panel-historical.csv\"" >> Expect.equal False
                        ]
                        content
            , test "the historical index links the shared downloads and its own, but not the live index's" <|
                \_ ->
                    let
                        content =
                            historyContent baseFlags
                    in
                    Expect.all
                        [ String.contains "href=\"../data/prints.csv\"" >> Expect.equal True
                        , String.contains "href=\"../data/series.csv\"" >> Expect.equal True
                        , String.contains "href=\"../data/panel-historical.csv\"" >> Expect.equal True
                        , String.contains "href=\"../data/panel-2026-09-28.csv\"" >> Expect.equal False
                        ]
                        content
            , test "an empty downloads list renders no Downloads section on either index page" <|
                \_ ->
                    let
                        flags =
                            { baseFlags | downloads = [] }
                    in
                    Expect.all
                        [ agentAccessibilityContent >> String.contains "Downloads" >> Expect.equal False
                        , historyContent >> String.contains "Downloads" >> Expect.equal False
                        ]
                        flags
            , test "a downloads list with nothing for this index renders no Downloads section" <|
                \_ ->
                    let
                        flags =
                            { baseFlags | downloads = [ historyOnlyDownload ] }
                    in
                    agentAccessibilityContent flags
                        |> String.contains "Downloads"
                        |> Expect.equal False
            , test "the about page's Reproducibility section links to the live index's downloads" <|
                \_ ->
                    aboutContent baseFlags
                        |> String.contains "href=\"../agent-accessibility/index.html\""
                        |> Expect.equal True
            ]
        , describe "the live index page still renders on its own"
            [ test "shows its own headline value, distinct from the historical series" <|
                \_ ->
                    agentAccessibilityContent baseFlags
                        |> String.contains "23.47%"
                        |> Expect.equal True
            , test "does not show the historical index's latest value" <|
                \_ ->
                    agentAccessibilityContent baseFlags
                        |> String.contains "27.85%"
                        |> Expect.equal False
            ]
        , describe "the methodology page"
            [ test "is present at agent-accessibility/methodology/index.html" <|
                \_ ->
                    Pages.pages baseFlags
                        |> List.map .path
                        |> List.member "agent-accessibility/methodology/index.html"
                        |> Expect.equal True
            , test "links home two directories up" <|
                \_ ->
                    methodologyContent baseFlags
                        |> String.contains "href=\"../../index.html\""
                        |> Expect.equal True
            , test "shows the collection window, provisional threshold and body cap from the fixture, not the real values" <|
                \_ ->
                    let
                        content =
                            methodologyContent baseFlags
                    in
                    Expect.all
                        [ String.contains "48" >> Expect.equal True
                        , String.contains "91.5" >> Expect.equal True
                        , String.contains "1.0 KB" >> Expect.equal True
                        ]
                        content
            , test "shows every fixture probe path" <|
                \_ ->
                    let
                        content =
                            methodologyContent baseFlags
                    in
                    Expect.all
                        (List.map (\path -> String.contains path >> Expect.equal True) baseMethodologyParameters.probePaths)
                        content
            , test "names the conclusive and unreadable outcomes" <|
                \_ ->
                    let
                        content =
                            methodologyContent baseFlags
                    in
                    Expect.all
                        [ String.contains "Fetched" >> Expect.equal True
                        , String.contains "NoRobotsTxt" >> Expect.equal True
                        , String.contains "Challenged" >> Expect.equal True
                        , String.contains "ServerError" >> Expect.equal True
                        ]
                        content
            , test "shows the user-agent read from flags, in code" <|
                \_ ->
                    methodologyContent baseFlags
                        |> String.contains "<code>TallyhouseIndexBot/1.0 (+https://allanderek.github.io/tallyhouse/about/crawler/)</code>"
                        |> Expect.equal True
            , test "links to the crawler's own page, two directories up" <|
                \_ ->
                    methodologyContent baseFlags
                        |> String.contains "href=\"../../about/crawler/index.html\""
                        |> Expect.equal True
            , test "shows a fixture methodology version's string, summary and why" <|
                \_ ->
                    let
                        content =
                            methodologyContent baseFlags
                    in
                    Expect.all
                        [ String.contains "agents=2;protego=0.6.2" >> Expect.equal True
                        , String.contains secondMethodologyVersion.summary >> Expect.equal True
                        , String.contains secondMethodologyVersion.why >> Expect.equal True
                        ]
                        content
            , test "describes a superseded version's periods as restated" <|
                \_ ->
                    let
                        content =
                            methodologyContent baseFlags
                    in
                    Expect.all
                        [ String.contains "2026-09-14" >> Expect.equal True
                        , String.contains "restated" >> Expect.equal True
                        ]
                        content
            , test "with undocumented versions, the warning names each one" <|
                \_ ->
                    let
                        flags =
                            { baseFlags | methodology = { baseMethodology | undocumented = [ "agents=9;protego=9.9.9" ] } }
                    in
                    methodologyContent flags
                        |> String.contains "agents=9;protego=9.9.9"
                        |> Expect.equal True
            , test "with no undocumented versions, no warning is rendered" <|
                \_ ->
                    methodologyContent baseFlags
                        |> String.contains "Published without a changelog entry"
                        |> Expect.equal False
            , test "links to the design documents in the repository" <|
                \_ ->
                    methodologyContent baseFlags
                        |> String.contains "href=\"https://github.com/allanderek/tallyhouse/tree/main/docs/superpowers/specs\""
                        |> Expect.equal True
            ]
        , describe "links to the methodology page"
            [ test "the live index links to it alongside the methodology version, at the right depth" <|
                \_ ->
                    agentAccessibilityContent baseFlags
                        |> String.contains "href=\"methodology/index.html\""
                        |> Expect.equal True
            , test "the about page links to it, one directory up and across" <|
                \_ ->
                    aboutContent baseFlags
                        |> String.contains "href=\"../agent-accessibility/methodology/index.html\""
                        |> Expect.equal True
            ]
        , describe "release pages"
            [ test "emits a release page for each fixture period of each index" <|
                \_ ->
                    let
                        paths =
                            Pages.pages baseFlags |> List.map .path
                    in
                    Expect.all
                        [ List.member "agent-accessibility/releases/2026-09-14/index.html" >> Expect.equal True
                        , List.member "agent-accessibility-history/releases/2023-01/index.html" >> Expect.equal True
                        , List.member "agent-accessibility-history/releases/2023-09/index.html" >> Expect.equal True
                        , List.member "agent-accessibility-history/releases/2026-08/index.html" >> Expect.equal True
                        ]
                        paths
            , test "a release page shows its own period's value and not another period's" <|
                \_ ->
                    let
                        flags =
                            { baseFlags | prints = [ baseRow, { baseRow | period = "2026-09-28", vintage = "1", value = "24.0964" } ] }

                        content =
                            releaseContent flags "agent-accessibility" "2026-09-28"
                    in
                    Expect.all
                        [ String.contains "24.10%" >> Expect.equal True
                        , String.contains "23.47%" >> Expect.equal False
                        ]
                        content
            , test "the historical release page shows its own period's value, not another's" <|
                \_ ->
                    let
                        content =
                            releaseContent baseFlags "agent-accessibility-history" "2023-09"
                    in
                    Expect.all
                        [ String.contains "15.93%" >> Expect.equal True
                        , String.contains "27.85%" >> Expect.equal False
                        , String.contains "1.28%" >> Expect.equal False
                        ]
                        content
            , test "shows provenance: vintage, methodology version and collector version" <|
                \_ ->
                    let
                        content =
                            releaseContent baseFlags "agent-accessibility" "2026-09-14"
                    in
                    Expect.all
                        [ String.contains baseRow.vintage >> Expect.equal True
                        , String.contains baseRow.methodologyVersion >> Expect.equal True
                        , String.contains baseRow.collectorVersion >> Expect.equal True
                        , String.contains baseRow.computedAt >> Expect.equal True
                        ]
                        content
            , test "the methodology version links to the methodology page, three levels deep" <|
                \_ ->
                    releaseContent baseFlags "agent-accessibility" "2026-09-14"
                        |> String.contains "href=\"../../../agent-accessibility/methodology/index.html\""
                        |> Expect.equal True
            , test "a period with a superseded vintage shows the earlier value and the reason" <|
                \_ ->
                    let
                        flags =
                            { baseFlags
                                | prints = [ { baseRow | vintage = "2", value = "23.9719", reason = "corrected a parser bug" } ]
                                , superseded = [ { baseRow | vintage = "1", value = "23.4704" } ]
                            }

                        content =
                            releaseContent flags "agent-accessibility" "2026-09-14"
                    in
                    Expect.all
                        [ String.contains "23.97%" >> Expect.equal True
                        , String.contains "23.47%" >> Expect.equal True
                        , String.contains "corrected a parser bug" >> Expect.equal True
                        , String.contains "never edited, only superseded" >> Expect.equal True
                        ]
                        content
            , test "a period with no superseded vintage says plainly that it was never restated" <|
                \_ ->
                    releaseContent baseFlags "agent-accessibility" "2026-09-14"
                        |> String.contains "has never been restated"
                        |> Expect.equal True
            , test "per-agent series rows link to the crawler pages, three levels deep" <|
                \_ ->
                    releaseContent baseFlags "agent-accessibility" "2026-09-14"
                        |> String.contains "href=\"../../../agent-accessibility/agents/gptbot/index.html\""
                        |> Expect.equal True
            , test "a token with no crawler page renders as plain text, not a broken link" <|
                \_ ->
                    let
                        flags =
                            { baseFlags
                                | agents = Dict.fromList [ ( "GPTBot", gptBot ) ]
                            }

                        content =
                            releaseContent flags "agent-accessibility" "2026-09-14"
                    in
                    Expect.all
                        [ String.contains "Claude-Web" >> Expect.equal True
                        , String.contains "href=\"../../../agent-accessibility/agents/claude-web/index.html\"" >> Expect.equal False
                        ]
                        content
            , test "a 2026-09-28-style release links its own per-period download" <|
                \_ ->
                    let
                        flags =
                            { baseFlags | prints = [ baseRow, { baseRow | period = "2026-09-28", vintage = "1" } ] }
                    in
                    releaseContent flags "agent-accessibility" "2026-09-28"
                        |> String.contains "panel-2026-09-28.csv"
                        |> Expect.equal True
            , test "a 2026-09-14-style release does not link the other period's download" <|
                \_ ->
                    let
                        flags =
                            { baseFlags | prints = [ baseRow, { baseRow | period = "2026-09-28", vintage = "1" } ] }
                    in
                    releaseContent flags "agent-accessibility" "2026-09-14"
                        |> String.contains "panel-2026-09-28.csv"
                        |> Expect.equal False
            , test "either way, the shared ledgers are always linked" <|
                \_ ->
                    let
                        flags =
                            { baseFlags | prints = [ baseRow, { baseRow | period = "2026-09-28", vintage = "1" } ] }
                    in
                    Expect.all
                        [ \_ -> releaseContent flags "agent-accessibility" "2026-09-14" |> String.contains "data/prints.csv" |> Expect.equal True
                        , \_ -> releaseContent flags "agent-accessibility" "2026-09-28" |> String.contains "data/series.csv" |> Expect.equal True
                        ]
                        ()
            , test "carries a suggested citation with the index title, period, value, vintage and canonical url" <|
                \_ ->
                    let
                        content =
                            releaseContent baseFlags "agent-accessibility" "2026-09-14"
                    in
                    Expect.all
                        [ String.contains "Suggested citation" >> Expect.equal True
                        , String.contains baseFlags.index.title >> Expect.equal True
                        , String.contains "2026-09-14" >> Expect.equal True
                        , String.contains "23.47%" >> Expect.equal True
                        , String.contains "vintage 1" >> Expect.equal True
                        , String.contains "https://allanderek.github.io/tallyhouse/agent-accessibility/releases/2026-09-14/index.html" >> Expect.equal True
                        ]
                        content
            , test "the releases index lists every period, newest first" <|
                \_ ->
                    releasesIndexContent baseFlags "agent-accessibility-history"
                        |> String.contains "<td><a href=\"2026-08/index.html\">2026-08</a></td>"
                        |> Expect.equal True
            , test "home links from a release page resolve three levels up" <|
                \_ ->
                    releaseContent baseFlags "agent-accessibility" "2026-09-14"
                        |> String.contains "href=\"../../../index.html\""
                        |> Expect.equal True
            , test "the live index page links to its releases index" <|
                \_ ->
                    agentAccessibilityContent baseFlags
                        |> String.contains "href=\"../agent-accessibility/releases/index.html\""
                        |> Expect.equal True
            , test "the historical index page links to its releases index" <|
                \_ ->
                    historyContent baseFlags
                        |> String.contains "href=\"../agent-accessibility-history/releases/index.html\""
                        |> Expect.equal True
            ]
        ]
