module Pages exposing (Page, pages)

{-| Builds the pages of the Tallyhouse site from the decoded site data.
Each `Page` is a relative path (no leading slash) and the rendered HTML
document to write there; `Site` collects them and sends them out its port.
-}

import Data exposing (Flags, Panel, Qualification, Row)
import Html exposing (Html)


type alias Page =
    { path : String
    , content : String
    }


pages : Flags -> List Page
pages flags =
    [ homePage flags
    , indexPage flags
    , aboutPage flags
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
                    [ [ pageHeader { title = flags.index.title, subtitle = Just flags.index.question }
                      , Html.main_ []
                            (List.concat
                                [ headlineSection flags.panel flags.prints
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
                [ pageHeader { title = "About Tallyhouse", subtitle = Nothing }
                , Html.main_ []
                    [ Html.section []
                        [ Html.h2 [] [ Html.text "What this measures" ]
                        , Html.p [] [ Html.text flags.index.question ]
                        , Html.p []
                            [ Html.text "Tallyhouse reads the "
                            , Html.code [] [ Html.text "robots.txt" ]
                            , Html.text " file published by each site in a fixed panel drawn from the Tranco top-sites list, and checks whether it names one of a fixed list of AI crawlers and disallows it. The headline figure is the share of the panel that does, published weekly."
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
                            [ Html.text
                                (String.concat
                                    [ "Panel "
                                    , flags.panel.trancoListId
                                    , ", captured "
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
                    ]
                , siteFooter
                ]
            }
    }



-- Shared chrome.


pageHeader : { title : String, subtitle : Maybe String } -> Html
pageHeader config =
    Html.header []
        (List.concat
            [ [ Html.p [ Html.attribute "class" "home-link" ]
                    [ Html.a [ Html.attribute "href" "../index.html" ] [ Html.text "Tallyhouse" ] ]
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
        , "table { border-collapse: collapse; width: 100%; margin: 1rem 0 2rem; font-size: 0.95rem; }"
        , "th, td { text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid #ddd; }"
        , "th { border-bottom: 2px solid #999; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.03em; color: #444; }"
        , ".series-table { margin-bottom: 1.5rem; }"
        , "footer { margin-top: 3rem; border-top: 1px solid #ddd; padding-top: 1rem; }"
        , "code { background: #f0f0ee; padding: 0.1rem 0.3rem; border-radius: 2px; }"
        ]
