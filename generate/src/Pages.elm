module Pages exposing (Page, pages)

{-| Builds the pages of the Tallyhouse site from the decoded site data.
Each `Page` is a relative path (no leading slash) and the rendered HTML
document to write there; `Site` collects them and sends them out its port.
-}

import Chart
import Data exposing (Agent, DivergentDomain, Flags, Operator, Panel, Qualification, Row, Stances)
import Dict exposing (Dict)
import Html exposing (Html)


type alias Page =
    { path : String
    , content : String
    }


pages : Flags -> List Page
pages flags =
    List.concat
        [ [ homePage flags
          , indexPage flags
          , agentsIndexPage flags
          ]
        , agentPageList flags
        , [ aboutPage flags ]
        ]



-- The site root.


homePage : Flags -> Page
homePage flags =
    { path = "index.html"
    , content =
        Html.document
            { title = "Tallyhouse"
            , description = "Tallyhouse is a weekly, reproducible index measuring how many of the top websites tell AI crawlers to stay out."
            , head = [ stylesheet ]
            , body =
                [ Html.header []
                    [ Html.h1 [] [ Html.text "Tallyhouse" ]
                    , Html.p [ Html.attribute "class" "tagline" ] [ Html.text flags.index.question ]
                    ]
                , Html.main_ []
                    [ Html.p []
                        [ Html.text "Tallyhouse measures how many of the top 1,000 websites name an AI crawler in "
                        , Html.code [] [ Html.text "robots.txt" ]
                        , Html.text " and disallow it, and publishes a new figure every week from a committed, append-only ledger."
                        ]
                    , Html.p []
                        [ Html.text "Read the "
                        , Html.a [ Html.attribute "href" "agent-accessibility/index.html" ] [ Html.text flags.index.title ]
                        , Html.text ", or see "
                        , Html.a [ Html.attribute "href" "about/index.html" ] [ Html.text "how it is built and why the numbers can be trusted" ]
                        , Html.text "."
                        ]
                    ]
                , siteFooter
                ]
            }
    }



-- The index page proper.


indexPage : Flags -> Page
indexPage flags =
    let
        period =
            Maybe.withDefault "" (Data.currentPeriod flags.prints)
    in
    { path = "agent-accessibility/index.html"
    , content =
        Html.document
            { title = flags.index.title
            , description = flags.index.question
            , head = [ stylesheet ]
            , body =
                List.concat
                    [ [ pageHeader { title = flags.index.title, subtitle = Just flags.index.question, homeHref = "../index.html" }
                      , Html.main_ []
                            (List.concat
                                [ headlineSection flags.panel flags.prints
                                , Chart.view flags.prints flags.series
                                , seriesSection flags.series period
                                , [ Html.section [ Html.attribute "class" "history" ]
                                        [ Html.h2 [] [ Html.text "Every published print" ]
                                        , printsTable flags.prints
                                        ]
                                  ]
                                , supersededSection flags.superseded flags.prints
                                ]
                            )
                      ]
                    , [ siteFooter ]
                    ]
            }
    }


headlineSection : Panel -> List Row -> List Html
headlineSection panel prints =
    case Data.latestPrint prints of
        Nothing ->
            [ Html.p [] [ Html.text "No print has been published yet." ] ]

        Just latest ->
            List.concat
                [ [ Html.section [ Html.attribute "class" "headline" ]
                        (List.concat
                            [ provisionalBadge latest
                            , [ Html.p [ Html.attribute "class" "headline-value" ]
                                    [ Html.text (Data.formatPercent latest.value) ]
                              , Html.p [ Html.attribute "class" "headline-caption" ]
                                    [ Html.text
                                        (String.concat
                                            [ "of the top "
                                            , String.fromInt panel.size
                                            , " websites name at least one AI crawler in robots.txt and disallow it, for the week of "
                                            , latest.period
                                            , "."
                                            ]
                                        )
                                    ]
                              , Html.p [ Html.attribute "class" "meta" ]
                                    [ Html.text
                                        (String.concat
                                            [ "Denominator: "
                                            , latest.denominator
                                            , " sites with a usable robots.txt verdict for this period. Coverage: "
                                            , Data.formatPercent latest.coverage
                                            , " of the panel. Methodology "
                                            , latest.methodologyVersion
                                            , ", collector "
                                            , latest.collectorVersion
                                            , "."
                                            ]
                                        )
                                    ]
                              ]
                            ]
                        )
                  ]
                , [ biasCallout panel.qualification ]
                ]


provisionalBadge : Row -> List Html
provisionalBadge row =
    case Data.isProvisional row of
        False ->
            []

        True ->
            [ Html.p [ Html.attribute "class" "provisional-badge" ]
                [ Html.text "PROVISIONAL — this figure has not been finalised and may be revised." ]
            ]


biasCallout : Qualification -> Html
biasCallout qualification =
    Html.section [ Html.attribute "class" "callout bias" ]
        [ Html.h2 [] [ Html.text "A known bias in this number" ]
        , Html.p [] [ Html.text qualification.knownBias ]
        , Html.p [ Html.attribute "class" "meta" ]
            [ Html.text
                (String.concat
                    [ String.fromInt qualification.excluded
                    , " of "
                    , String.fromInt qualification.candidatesExamined
                    , " candidate sites examined were excluded from the panel before this figure was computed, most often for failing to answer at all."
                    ]
                )
            ]
        ]


printsTable : List Row -> Html
printsTable prints =
    Html.table [ Html.attribute "class" "prints" ]
        [ Html.thead []
            [ Html.tr []
                [ Html.th [] [ Html.text "Period" ]
                , Html.th [] [ Html.text "Value" ]
                , Html.th [] [ Html.text "Coverage" ]
                , Html.th [] [ Html.text "Status" ]
                ]
            ]
        , Html.tbody [] (List.map printRow (List.reverse prints))
        ]


printRow : Row -> Html
printRow row =
    Html.tr []
        [ Html.td [] [ Html.text row.period ]
        , Html.td [] [ Html.text (Data.formatPercent row.value) ]
        , Html.td [] [ Html.text (Data.formatPercent row.coverage) ]
        , Html.td [] [ Html.text (statusLabel row) ]
        ]


statusLabel : Row -> String
statusLabel row =
    case Data.isProvisional row of
        False ->
            "Final"

        True ->
            "Provisional"


seriesSection : List Row -> String -> List Html
seriesSection allSeries period =
    let
        current =
            List.filter (\row -> row.period == period) allSeries

        fixed =
            List.filter (\row -> not (Data.isAgentSeries row)) current

        agents =
            List.filter Data.isAgentSeries current
    in
    [ Html.section [ Html.attribute "class" "series" ]
        [ Html.h2 [] [ Html.text "Sub-series for this period" ]
        , Html.p []
            [ Html.text "The headline figure counts sites that "
            , Html.node "strong" [] [ Html.text "name" ]
            , Html.text " at least one AI crawler in robots.txt and disallow it — a "
            , Html.code [] [ Html.text "targeted" ]
            , Html.text " block. It does not by itself include sites closed to "
            , Html.node "em" [] [ Html.text "every" ]
            , Html.text " crawler by a blanket rule; the "
            , Html.code [] [ Html.text "effective" ]
            , Html.text " row below adds those in, so targeted and effective access are not the same number."
            ]
        , Html.p []
            [ Html.text "The "
            , Html.code [] [ Html.text "coverage" ]
            , Html.text " row is not a share of the web; it is the share of the panel this period's headline figure actually rests on. A site counts as conclusively observed if it served a usable "
            , Html.code [] [ Html.text "robots.txt" ]
            , Html.text ", or definitively answered that it has none, with a 404. Sites that timed out, refused the request, or sat behind an anti-automation challenge are excluded from both the numerator and the denominator of the headline — counted as neither compliant nor non-compliant."
            ]
        , seriesTable "Fixed series" fixed (\row -> Data.seriesLabel (Maybe.withDefault "" row.seriesId))
        , seriesTable "Per-agent series" agents Data.agentName
        ]
    ]


seriesTable : String -> List Row -> (Row -> String) -> Html
seriesTable title rows labelOf =
    Html.div [ Html.attribute "class" "series-table" ]
        [ Html.h3 [] [ Html.text title ]
        , Html.table []
            [ Html.thead []
                [ Html.tr []
                    [ Html.th [] [ Html.text "Series" ]
                    , Html.th [] [ Html.text "Value" ]
                    ]
                ]
            , Html.tbody [] (List.map (seriesRow labelOf) (List.sortBy labelOf rows))
            ]
        ]


seriesRow : (Row -> String) -> Row -> Html
seriesRow labelOf row =
    Html.tr []
        [ Html.td [] [ Html.text (labelOf row) ]
        , Html.td [] [ Html.text (Data.formatPercent row.value) ]
        ]


supersededSection : List Row -> List Row -> List Html
supersededSection superseded latestPrints =
    case superseded of
        [] ->
            []

        _ ->
            [ Html.section [ Html.attribute "class" "callout superseded" ]
                [ Html.h2 [] [ Html.text "Restated periods" ]
                , Html.p [] [ Html.text "These periods were published, then revised. Nothing is deleted from the record: the earlier value is kept alongside the reason it changed." ]
                , Html.table []
                    [ Html.thead []
                        [ Html.tr []
                            [ Html.th [] [ Html.text "Period" ]
                            , Html.th [] [ Html.text "Old value" ]
                            , Html.th [] [ Html.text "New value" ]
                            , Html.th [] [ Html.text "Reason" ]
                            ]
                        ]
                    , Html.tbody [] (List.map (restatementRow latestPrints) (Data.latestByPeriod superseded))
                    ]
                ]
            ]


restatementRow : List Row -> Row -> Html
restatementRow latestPrints old =
    case Data.findByPeriod old.period latestPrints of
        Nothing ->
            Html.tr []
                [ Html.td [] [ Html.text old.period ]
                , Html.td [] [ Html.text (Data.formatPercent old.value) ]
                , Html.td [] [ Html.text "—" ]
                , Html.td [] [ Html.text "—" ]
                ]

        Just current ->
            Html.tr []
                [ Html.td [] [ Html.text old.period ]
                , Html.td [] [ Html.text (Data.formatPercent old.value) ]
                , Html.td [] [ Html.text (Data.formatPercent current.value) ]
                , Html.td [] [ Html.text current.reason ]
                ]



-- The about page.


aboutPage : Flags -> Page
aboutPage flags =
    { path = "about/index.html"
    , content =
        Html.document
            { title = "About Tallyhouse"
            , description = "What Tallyhouse measures, how its panel is built, and why every published number can be reproduced from the committed ledger."
            , head = [ stylesheet ]
            , body =
                [ pageHeader { title = "About Tallyhouse", subtitle = Nothing, homeHref = "../index.html" }
                , Html.main_ []
                    [ Html.section []
                        [ Html.h2 [] [ Html.text "What this measures" ]
                        , Html.p [] [ Html.text flags.index.question ]
                        , Html.p []
                            [ Html.text "Tallyhouse reads the "
                            , Html.code [] [ Html.text "robots.txt" ]
                            , Html.text " file published by each site in a fixed panel drawn from the "
                            , Html.a [ Html.attribute "href" "https://tranco-list.eu/" ] [ Html.text "Tranco" ]
                            , Html.text " top-sites list, and checks whether it names one of a fixed list of AI crawlers and disallows it. The headline figure is the share of the panel that does, published weekly."
                            ]
                        , Html.p []
                            [ Html.text "Tranco is a research-grade ranking of the most popular domains, built by combining several underlying popularity sources and published daily. Each day's list carries a permanent identifier, so a specific list can be cited and retrieved later — which is what lets a reader check our panel against the exact list we drew it from, rather than take our word for it."
                            ]
                        ]
                    , Html.section []
                        [ Html.h2 [] [ Html.text "Reproducibility" ]
                        , Html.p []
                            [ Html.text "Every number this site publishes is read back from a committed, append-only ledger, never recomputed at render time. Cloning the repository and re-running the collector against the recorded panel reproduces every published figure exactly. When a value has to change, it is appended as a new vintage alongside a stated reason — the earlier value is never edited or deleted." ]
                        ]
                    , Html.section []
                        [ Html.h2 [] [ Html.text "How the panel is built" ]
                        , Html.p []
                            [ Html.text "Panel "
                            , Html.a
                                [ Html.attribute "href" (String.concat [ "https://tranco-list.eu/list/", flags.panel.trancoListId ]) ]
                                [ Html.text flags.panel.trancoListId ]
                            , Html.text
                                (String.concat
                                    [ ", captured "
                                    , flags.panel.captured
                                    , ": "
                                    , flags.panel.qualification.rule
                                    , "."
                                    ]
                                )
                            ]
                        , Html.p []
                            [ Html.text
                                (String.concat
                                    [ String.fromInt flags.panel.qualification.excluded
                                    , " of "
                                    , String.fromInt flags.panel.qualification.candidatesExamined
                                    , " candidates examined were excluded, leaving a qualified panel of "
                                    , String.fromInt flags.panel.qualification.qualified
                                    , " sites."
                                    ]
                                )
                            ]
                        , Html.p [ Html.attribute "class" "meta" ] [ Html.text flags.panel.qualification.knownBias ]
                        ]
                    , Html.section []
                        [ Html.h2 [] [ Html.text "Related work" ]
                        , Html.p []
                            [ Html.text "Tallyhouse is not the only project measuring this ground. "
                            , Html.a [ Html.attribute "href" "https://knownagents.com/insights" ] [ Html.text "The Agentic Web Index" ]
                            , Html.text ", published by Known Agents, tracks the same crawlers from the opposite side: not what a site's "
                            , Html.code [] [ Html.text "robots.txt" ]
                            , Html.text " says, but what a crawler actually does when it requests a page."
                            ]
                        , Html.p []
                            [ Html.text "Known Agents draws on server-side traffic from more than 5,000 websites running its analytics, which lets it observe agent-versus-human traffic, bot spoofing, and, where Tallyhouse cannot follow, robots.txt compliance: whether a crawler honours the rule it was given. Tallyhouse reads the rule from outside; it has no way to see whether anyone obeys it. A reader who wants to know whether a crawler actually obeys a disallow, rather than whether one was published, should look there." ]
                        , Html.p []
                            [ Html.text "The two panels are built for different questions, and neither design is wrong for its own. Known Agents' sample is self-selected, drawn from sites that adopted its product, and it says so plainly: "
                            , Html.text "\"Participating websites are not a random sample, and the qualifying set changes over time, so results show observed directional trends rather than a census of global web traffic.\""
                            , Html.text " Tallyhouse's panel is fixed for the year and drawn from an external ranking with a citable list identifier, so a change in the headline number cannot be a change in who is being measured. That is a difference in design goal, not a defect in theirs: a daily operational index and a slow, reproducible one are built to answer different questions."
                            ]
                        , Html.p []
                            [ Html.text "Known Agents publishes no raw data downloads; Tallyhouse publishes the collected "
                            , Html.code [] [ Html.text "robots.txt" ]
                            , Html.text " bodies, the ledger, and the code behind every figure, so a stranger can re-derive any number published here. Known Agents updates daily; Tallyhouse prints weekly and freezes each print. Together the two say more than either alone: they measure what crawlers do, we measure what sites ask for."
                            ]
                        ]
                    ]
                , siteFooter
                ]
            }
    }



-- The agent directory: all 45 tracked tokens, grouped by operator.


agentsIndexPage : Flags -> Page
agentsIndexPage flags =
    { path = "agent-accessibility/agents/index.html"
    , content =
        Html.document
            { title = "AI Crawlers"
            , description = "Every AI crawler and consent token Tallyhouse tracks, grouped by the operator that runs it, with the published block rate for each."
            , head = [ stylesheet ]
            , body =
                List.concat
                    [ [ pageHeader
                            { title = "AI Crawlers"
                            , subtitle = Just "All tracked tokens, grouped by operator."
                            , homeHref = "../../index.html"
                            }
                      , Html.main_ []
                            (List.concat
                                [ [ Html.p []
                                        [ Html.text "An operator often runs several tokens for different jobs — training, search, or a fetch a user asked for — and sites choose to treat them differently on purpose. "
                                        , Html.a [ Html.attribute "href" "../index.html" ] [ Html.text "The headline figure" ]
                                        , Html.text " counts a targeted block once no matter how many tokens are involved; these pages show what was actually chosen, token by token."
                                        ]
                                  ]
                                , operatorSections flags
                                ]
                            )
                      ]
                    , [ siteFooter ]
                    ]
            }
    }


operatorSections : Flags -> List Html
operatorSections flags =
    let
        period =
            Maybe.withDefault "" (Data.currentPeriod flags.prints)
    in
    List.map (operatorSection flags period) (Dict.values flags.operators)


operatorSection : Flags -> String -> Operator -> Html
operatorSection flags period operator =
    Html.section [ Html.attribute "class" "operator" ]
        (List.concat
            [ [ Html.h2 [] [ Html.text operator.name ]
              , Html.p [] [ Html.text operator.description ]
              ]
            , divergenceCallout operator
            , [ Html.table []
                    [ Html.thead []
                        [ Html.tr []
                            [ Html.th [] [ Html.text "Token" ]
                            , Html.th [] [ Html.text "Purpose" ]
                            , Html.th [] [ Html.text "Published rate" ]
                            ]
                        ]
                    , Html.tbody [] (List.filterMap (directoryRow flags period) operator.tokens)
                    ]
              ]
            ]
        )


divergenceCallout : Operator -> List Html
divergenceCallout operator =
    case operator.divergentCount > 0 of
        False ->
            []

        True ->
            [ Html.p [ Html.attribute "class" "meta" ]
                [ Html.text
                    (String.concat
                        [ String.fromInt operator.divergentCount
                        , " domains in the panel set "
                        , operator.name
                        , "'s tokens differently from one another."
                        ]
                    )
                ]
            ]


directoryRow : Flags -> String -> String -> Maybe Html
directoryRow flags period token =
    Dict.get token flags.agents
        |> Maybe.map
            (\agent ->
                Html.tr []
                    [ Html.td [] [ Html.a [ Html.attribute "href" (String.concat [ "../agent/", agent.slug, "/index.html" ]) ] [ Html.text agent.token ] ]
                    , Html.td [] [ Html.text (Data.purposeLabel agent.purpose) ]
                    , Html.td [] [ Html.text (publishedRate flags period agent) ]
                    ]
            )


{-| An agent's published rate for the given period, formatted as a
percentage, or an em dash when the current period has none.
-}
publishedRate : Flags -> String -> Agent -> String
publishedRate flags period agent =
    Data.findBySeriesAndPeriod agent.seriesId period flags.series
        |> Maybe.map (\row -> Data.formatPercent row.value)
        |> Maybe.withDefault "—"



-- One page per tracked token.


agentPageList : Flags -> List Page
agentPageList flags =
    flags.agents
        |> Dict.values
        |> List.map (agentPage flags)


agentPage : Flags -> Agent -> Page
agentPage flags agent =
    { path = String.concat [ "agent-accessibility/agent/", agent.slug, "/index.html" ]
    , content =
        Html.document
            { title = agent.token
            , description = agent.description
            , head = [ stylesheet ]
            , body =
                List.concat
                    [ [ pageHeader
                            { title = agent.token
                            , subtitle = Just (String.concat [ agent.operator, " — ", Data.purposeLabel agent.purpose ])
                            , homeHref = "../../../index.html"
                            }
                      , Html.main_ []
                            (List.concat
                                [ [ agentNav ]
                                , purposeNotice agent
                                , [ purposeParagraph flags.purposes agent
                                  , Html.p [] [ Html.text agent.description ]
                                  ]
                                , agentRateSection flags agent
                                , stanceSection agent
                                , siblingsSection flags agent
                                , divergenceSection flags agent
                                ]
                            )
                      ]
                    , [ siteFooter ]
                    ]
            }
    }


agentNav : Html
agentNav =
    Html.p [ Html.attribute "class" "meta" ]
        [ Html.a [ Html.attribute "href" "../../agents/index.html" ] [ Html.text "All crawlers" ]
        , Html.text " · "
        , Html.a [ Html.attribute "href" "../../index.html" ] [ Html.text "Agent Accessibility Index" ]
        ]


purposeParagraph : Dict String String -> Agent -> Html
purposeParagraph purposes agent =
    Html.p []
        [ Html.node "strong" [] [ Html.text "Purpose: " ]
        , Html.text (Data.purposeLabel agent.purpose)
        , Html.text ". "
        , Html.text (Maybe.withDefault "" (Dict.get agent.purpose purposes))
        ]


{-| An unmissable callout for the two cases readers most often get wrong:
`Google-Extended` and `Applebot-Extended` are not crawlers at all, and
`Claude-Web`'s purpose is not established with confidence.
-}
purposeNotice : Agent -> List Html
purposeNotice agent =
    case agent.purpose of
        "training-consent" ->
            [ Html.section [ Html.attribute "class" "callout notice" ]
                [ Html.h2 [] [ Html.text "Not a crawler" ]
                , Html.p []
                    [ Html.node "strong" [] [ Html.text agent.token ]
                    , Html.text " does not fetch pages. Disallowing it does not reduce crawling — it only withholds permission to train on content a conventional crawler already fetched."
                    ]
                ]
            ]

        "uncertain" ->
            [ Html.section [ Html.attribute "class" "callout notice" ]
                [ Html.h2 [] [ Html.text "Purpose not established" ]
                , Html.p [] [ Html.text "This token is tracked because sites still act on it, not because its purpose is known with confidence." ]
                ]
            ]

        _ ->
            []


agentRateSection : Flags -> Agent -> List Html
agentRateSection flags agent =
    let
        period =
            Maybe.withDefault "" (Data.currentPeriod flags.prints)
    in
    [ Html.section [ Html.attribute "class" "headline" ]
        (agentRateContent period (Data.findBySeriesAndPeriod agent.seriesId period flags.series))
    ]


agentRateContent : String -> Maybe Row -> List Html
agentRateContent period maybeRow =
    case maybeRow of
        Nothing ->
            [ Html.p [] [ Html.text "No published rate yet for this period." ] ]

        Just row ->
            List.concat
                [ provisionalBadge row
                , [ Html.p [ Html.attribute "class" "headline-value" ] [ Html.text (Data.formatPercent row.value) ]
                  , Html.p [ Html.attribute "class" "headline-caption" ]
                        [ Html.text
                            (String.concat
                                [ "of the panel names this token in robots.txt and disallows it, for the week of "
                                , row.period
                                , "."
                                ]
                            )
                        ]
                  ]
                ]


type alias StanceRow =
    { label : String
    , count : Int
    , explanation : String
    }


stanceRows : Stances -> List StanceRow
stanceRows stances =
    [ { label = "FullBlock", count = stances.fullBlock, explanation = "Every path is disallowed for this token." }
    , { label = "PartialBlock", count = stances.partialBlock, explanation = "Some paths are disallowed for this token; others are not." }
    , { label = "Allowed", count = stances.allowed, explanation = "The token is named and explicitly allowed." }
    , { label = "Unmentioned", count = stances.unmentioned, explanation = "The file never names this token. This is not consent — the site may still close it off with a blanket rule for every crawler." }
    ]


stanceSection : Agent -> List Html
stanceSection agent =
    [ Html.section [ Html.attribute "class" "stances" ]
        [ Html.h2 [] [ Html.text "How sites treat this token" ]
        , Html.table []
            [ Html.thead []
                [ Html.tr []
                    [ Html.th [] [ Html.text "Stance" ]
                    , Html.th [] [ Html.text "Domains" ]
                    , Html.th [] [ Html.text "What it means" ]
                    ]
                ]
            , Html.tbody [] (List.map stanceTableRow (stanceRows agent.stances))
            ]
        ]
    ]


stanceTableRow : StanceRow -> Html
stanceTableRow row =
    Html.tr []
        [ Html.td [] [ Html.text row.label ]
        , Html.td [] [ Html.text (String.fromInt row.count) ]
        , Html.td [] [ Html.text row.explanation ]
        ]


siblingsSection : Flags -> Agent -> List Html
siblingsSection flags agent =
    case Dict.get agent.operator flags.operators of
        Nothing ->
            []

        Just operator ->
            siblingsSectionFor flags agent operator (List.filter (\token -> token /= agent.token) operator.tokens)


siblingsSectionFor : Flags -> Agent -> Operator -> List String -> List Html
siblingsSectionFor flags agent operator siblingTokens =
    case siblingTokens of
        [] ->
            []

        _ ->
            let
                period =
                    Maybe.withDefault "" (Data.currentPeriod flags.prints)
            in
            [ Html.section [ Html.attribute "class" "siblings" ]
                [ Html.h2 [] [ Html.text (String.concat [ operator.name, "'s other tokens" ]) ]
                , Html.p [] [ Html.text operator.description ]
                , Html.table []
                    [ Html.thead []
                        [ Html.tr []
                            [ Html.th [] [ Html.text "Token" ]
                            , Html.th [] [ Html.text "Purpose" ]
                            , Html.th [] [ Html.text "Published rate" ]
                            ]
                        ]
                    , Html.tbody [] (List.filterMap (siblingRow flags period) siblingTokens)
                    ]
                ]
            ]


siblingRow : Flags -> String -> String -> Maybe Html
siblingRow flags period token =
    Dict.get token flags.agents
        |> Maybe.map
            (\sibling ->
                Html.tr []
                    [ Html.td [] [ Html.a [ Html.attribute "href" (String.concat [ "../", sibling.slug, "/index.html" ]) ] [ Html.text sibling.token ] ]
                    , Html.td [] [ Html.text (Data.purposeLabel sibling.purpose) ]
                    , Html.td [] [ Html.text (publishedRate flags period sibling) ]
                    ]
            )


divergenceSection : Flags -> Agent -> List Html
divergenceSection flags agent =
    case Dict.get agent.operator flags.operators of
        Nothing ->
            []

        Just operator ->
            divergenceSectionFor operator operator.divergentExamples


divergenceSectionFor : Operator -> List DivergentDomain -> List Html
divergenceSectionFor operator examples =
    case examples of
        [] ->
            []

        _ ->
            [ Html.section [ Html.attribute "class" "divergence" ]
                [ Html.h2 [] [ Html.text "Sites that treat these tokens differently" ]
                , Html.p [] [ Html.text (divergenceCaption operator examples) ]
                , Html.div [ Html.attribute "class" "table-scroll" ]
                    [ Html.table []
                        [ Html.thead [] [ divergenceHeaderRow operator.tokens ]
                        , Html.tbody [] (List.map (divergenceTableRow operator.tokens) examples)
                        ]
                    ]
                ]
            ]


divergenceCaption : Operator -> List DivergentDomain -> String
divergenceCaption operator examples =
    let
        shown =
            List.length examples
    in
    case operator.divergentCount > shown of
        True ->
            String.concat
                [ String.fromInt operator.divergentCount
                , " domains in the panel treat "
                , operator.name
                , "'s tokens differently from one another. The first "
                , String.fromInt shown
                , " are shown below."
                ]

        False ->
            String.concat
                [ String.fromInt operator.divergentCount
                , " domains in the panel treat "
                , operator.name
                , "'s tokens differently from one another."
                ]


divergenceHeaderRow : List String -> Html
divergenceHeaderRow tokens =
    Html.tr [] (Html.th [] [ Html.text "Domain" ] :: List.map (\token -> Html.th [] [ Html.text token ]) tokens)


divergenceTableRow : List String -> DivergentDomain -> Html
divergenceTableRow tokens example =
    Html.tr []
        (Html.td [] [ Html.text example.domain ]
            :: List.map (\token -> Html.td [] [ Html.text (Maybe.withDefault "—" (Dict.get token example.stances)) ]) tokens
        )



-- Shared chrome.


pageHeader : { title : String, subtitle : Maybe String, homeHref : String } -> Html
pageHeader config =
    Html.header []
        (List.concat
            [ [ Html.p [ Html.attribute "class" "home-link" ]
                    [ Html.a [ Html.attribute "href" config.homeHref ] [ Html.text "Tallyhouse" ] ]
              , Html.h1 [] [ Html.text config.title ]
              ]
            , subtitleHtml config.subtitle
            ]
        )


subtitleHtml : Maybe String -> List Html
subtitleHtml maybeSubtitle =
    case maybeSubtitle of
        Nothing ->
            []

        Just subtitle ->
            [ Html.p [ Html.attribute "class" "tagline" ] [ Html.text subtitle ] ]


siteFooter : Html
siteFooter =
    Html.footer []
        [ Html.p [ Html.attribute "class" "meta" ]
            [ Html.text "Tallyhouse. Every figure on this site is read from a committed ledger, not recomputed at render time." ]
        ]


stylesheet : Html
stylesheet =
    Html.node "style" [] [ Html.raw css ]


css : String
css =
    String.concat
        [ "body { font-family: Georgia, 'Times New Roman', serif; line-height: 1.65; color: #1a1a1a; background: #fdfdfb; max-width: 42rem; margin: 0 auto; padding: 2.5rem 1.25rem 4rem; }"
        , "h1, h2, h3, .home-link, th { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }"
        , "h1 { font-size: 1.9rem; line-height: 1.25; margin-bottom: 0.25rem; }"
        , "h2 { font-size: 1.3rem; margin-top: 2.5rem; }"
        , "h3 { font-size: 1.05rem; }"
        , ".tagline { color: #555; font-size: 1.05rem; margin-top: 0; }"
        , ".home-link a { text-decoration: none; color: #555; font-size: 0.9rem; text-transform: uppercase; letter-spacing: 0.04em; }"
        , "a { color: #1a4d8f; }"
        , ".headline { margin: 2rem 0; padding: 1.5rem; border: 1px solid #ddd; background: #f7f6f2; }"
        , ".headline-value { font-size: 3.2rem; font-weight: 700; margin: 0.5rem 0 0; line-height: 1; }"
        , ".headline-caption { font-size: 1.1rem; margin: 0.5rem 0; }"
        , ".meta { color: #555; font-size: 0.9rem; }"
        , ".provisional-badge { display: inline-block; background: #fff3cd; border: 1px solid #e6c200; color: #6b5900; font-weight: 700; padding: 0.3rem 0.7rem; border-radius: 3px; font-size: 0.85rem; letter-spacing: 0.03em; }"
        , ".callout { margin: 2rem 0; padding: 1.25rem 1.5rem; border-left: 4px solid #888; background: #f4f4f2; }"
        , ".callout.bias { border-left-color: #b5442e; }"
        , ".callout.superseded { border-left-color: #8a6d00; }"
        , ".callout.notice { border-left-color: #1a4d8f; }"
        , "table { border-collapse: collapse; width: 100%; margin: 1rem 0 2rem; font-size: 0.95rem; }"
        , "th, td { text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid #ddd; }"
        , "th { border-bottom: 2px solid #999; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.03em; color: #444; }"
        , ".series-table { margin-bottom: 1.5rem; }"
        , ".operator { margin: 2rem 0; }"
        , ".table-scroll { overflow-x: auto; }"
        , ".trend-chart { display: block; width: 100%; height: auto; margin-top: 0.5rem; }"
        , ".chart-axis-label { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 11px; fill: #555; font-variant-numeric: tabular-nums; }"
        , ".chart-endpoint-label { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 13px; font-weight: 700; font-variant-numeric: tabular-nums; }"
        , ".chart-legend { list-style: none; padding: 0; margin: 0.75rem 0 1.5rem; display: flex; flex-wrap: wrap; gap: 0.5rem 1.5rem; font-size: 0.9rem; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }"
        , ".chart-legend li { display: flex; align-items: center; gap: 0.4rem; }"
        , ".chart-swatch { display: inline-block; width: 0.8rem; height: 0.8rem; border-radius: 50%; flex: none; }"
        , ".chart-swatch-targeted { background: #2a78d6; }"
        , ".chart-swatch-effective { background: #eb6834; }"
        , ".chart-swatch-provisional { background: none; border: 2px solid #888; box-sizing: border-box; }"
        , "footer { margin-top: 3rem; border-top: 1px solid #ddd; padding-top: 1rem; }"
        , "code { background: #f0f0ee; padding: 0.1rem 0.3rem; border-radius: 2px; }"
        ]
