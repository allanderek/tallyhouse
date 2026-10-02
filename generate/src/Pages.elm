module Pages exposing (Page, pages)

{-| Builds the pages of the Tallyhouse site from the decoded site data.
Each `Page` is a relative path (no leading slash) and the rendered HTML
document to write there; `Site` collects them and sends them out its port.
-}

import Chart
import Data exposing (Agent, Crawl, CrawlEndpoint, Crawler, DivergentDomain, Download, Flags, History, HistoryPanel, Operator, Panel, PanelConstruction, Qualification, Row, Stances)
import Dict exposing (Dict)
import Html exposing (Html)
import Json.Encode as Encode


type alias Page =
    { path : String
    , content : String
    }


{-| Append the terminating full stop that the data deliberately omits (so
punctuation stays in the markup, not the stored strings).
-}
sentence : String -> String
sentence text =
    String.concat [ text, "." ]


pages : Flags -> List Page
pages flags =
    List.concat
        [ [ homePage flags
          , indexPage flags
          , historyPage flags
          , agentsIndexPage flags
          ]
        , agentPageList flags
        , [ aboutPage flags, crawlerPage flags, crawlerIpsPage flags ]
        ]



-- The site root.


homePage : Flags -> Page
homePage flags =
    { path = "index.html"
    , content =
        Html.document
            { title = "Tallyhouse"
            , description = "Tallyhouse tracks how many of the top websites tell AI crawlers to stay out: a three-year historical series, and a weekly reproducible index."
            , head = [ stylesheet ]
            , body =
                List.concat
                    [ [ Html.header []
                            [ Html.h1 [] [ Html.text "Tallyhouse" ]
                            , Html.p [ Html.attribute "class" "tagline" ] [ Html.text flags.index.question ]
                            ]
                      , Html.main_ []
                            (List.concat
                                [ leadSection flags.history
                                , Chart.view { cadence = "quarterly" } flags.history.prints flags.history.series
                                , onwardSection flags
                                , [ comparabilityCaution flags.history.panel.construction ]
                                , [ Html.p []
                                        [ Html.a [ Html.attribute "href" "about/index.html" ]
                                            [ Html.text "How it is built and why the numbers can be trusted" ]
                                        ]
                                  ]
                                ]
                            )
                      ]
                    , [ siteFooter ]
                    ]
            }
    }


{-| The lead prose: what the three-year series shows, with every number read
from `flags.history` rather than written into the page. The first sentence
deliberately avoids a fraction that the data itself could contradict — see
`shareDescription`.
-}
leadSection : History -> List Html
leadSection history =
    case ( Data.earliestPrint history.prints, Data.latestPrint history.prints, Data.biggestMove history.series ) of
        ( Just earliest, Just latest, Just move ) ->
            [ Html.p []
                [ Html.text "Three years ago almost no major website told AI crawlers to stay out. By "
                , Html.text latest.period
                , Html.text ", "
                , Html.text (shareDescription (rowValue latest))
                , Html.text " did — and the change was not gradual."
                ]
            , Html.p []
                [ Html.text "A fixed panel of "
                , Html.text (String.fromInt history.panel.size)
                , Html.text " long-running popular sites, read from Common Crawl's archive, stood at "
                , Html.text (Data.formatPercent earliest.value)
                , Html.text " in "
                , Html.text earliest.period
                , Html.text ". The largest single move in the series is "
                , Html.text move.period
                , Html.text ", up "
                , Html.text (Data.formatFixed2 (rowValue move))
                , Html.text " points on the reading before it — the first snapshot taken after OpenAI launched GPTBot in August 2023. The figure reached "
                , Html.text (Data.formatPercent latest.value)
                , Html.text " by "
                , Html.text latest.period
                , Html.text "."
                ]
            ]

        _ ->
            [ Html.p [] [ Html.text "The three-year historical series has not been published yet." ] ]


{-| A rough, honest fraction of the panel, derived from the actual latest
figure rather than asserted regardless of it — so this sentence cannot end up
contradicting the number that follows it, whatever the data turns out to say.
-}
shareDescription : Float -> String
shareDescription value =
    case value >= 25 of
        True ->
            "more than a quarter"

        False ->
            case value >= 10 of
                True ->
                    "more than a tenth"

                False ->
                    "still a small share"


{-| A `Row`'s `value` as a `Float`, falling back to `0` if it does not parse —
consistent with `formatPercent`'s fallback of showing the raw string rather
than crashing.
-}
rowValue : Row -> Float
rowValue row =
    Maybe.withDefault 0 (String.toFloat row.value)


onwardSection : Flags -> List Html
onwardSection flags =
    [ Html.section []
        (List.concat
            [ liveIndexParagraph flags (Data.latestPrint flags.prints)
            , [ Html.p []
                    [ Html.text "Read "
                    , Html.a [ Html.attribute "href" "agent-accessibility-history/index.html" ] [ Html.text flags.history.title ]
                    , Html.text " for the full three-year series and the method behind it."
                    ]
              ]
            ]
        )
    ]


liveIndexParagraph : Flags -> Maybe Row -> List Html
liveIndexParagraph flags maybeLatest =
    case maybeLatest of
        Nothing ->
            [ Html.p []
                [ Html.text "The weekly "
                , Html.a [ Html.attribute "href" "agent-accessibility/index.html" ] [ Html.text flags.index.title ]
                , Html.text " has not published a print yet."
                ]
            ]

        Just latest ->
            [ Html.p []
                [ Html.text "The weekly "
                , Html.a [ Html.attribute "href" "agent-accessibility/index.html" ] [ Html.text flags.index.title ]
                , Html.text " currently reads "
                , Html.text (Data.formatPercent latest.value)
                , Html.text " for the week of "
                , Html.text latest.period
                , Html.text "."
                ]
            ]


{-| The two indices read different panels, so a level on one is never a level
on the other. `notComparable` is the ledger's own account of that limit, read
back rather than restated here.
-}
comparabilityCaution : PanelConstruction -> Html
comparabilityCaution construction =
    Html.p [ Html.attribute "class" "meta" ]
        [ Html.text (String.concat [ "Note: ", construction.notComparable, "." ]) ]



-- The index page proper.


indexPage : Flags -> Page
indexPage flags =
    let
        period =
            Maybe.withDefault "" (Data.currentPeriod flags.prints)

        path =
            "agent-accessibility/index.html"
    in
    { path = path
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
                                , Chart.view { cadence = "weekly" } flags.prints flags.series
                                , seriesSection flags.series period
                                , [ Html.section [ Html.attribute "class" "history" ]
                                        [ Html.h2 [] [ Html.text "Every published print" ]
                                        , printsTable flags.prints
                                        ]
                                  ]
                                , supersededSection flags.superseded flags.prints
                                , downloadsSection path (Data.downloadsFor flags.index.id flags.downloads)
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
        , Html.p [] [ Html.text (sentence qualification.knownBias) ]
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
                , Html.th [] [ Html.text "Targeted" ]
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



-- Downloads: the CSV files Python writes alongside the site. Shared between
-- the live and historical index pages, each of which is one directory below
-- the site root, so a download's root-relative `path` needs one `../`
-- stepped off before it resolves from either page.


{-| The "Downloads" section listed on both index pages (spec 7: CSV downloads
are the site's only data interface). Omitted entirely rather than rendered
as an empty table when there is nothing to list, since an empty table would
look like a broken feature rather than an absent one.
-}
downloadsSection : String -> List Download -> List Html
downloadsSection ownPath downloads =
    case downloads of
        [] ->
            []

        _ ->
            [ Html.section [ Html.attribute "class" "downloads" ]
                [ Html.h2 [] [ Html.text "Downloads" ]
                , Html.p []
                    [ Html.text "Every figure published on this site can be re-derived from these files. The two ledgers below are served as the exact bytes committed to the repository, not regenerated." ]
                , downloadsTable ownPath downloads
                ]
            ]


downloadsTable : String -> List Download -> Html
downloadsTable ownPath downloads =
    Html.table []
        [ Html.thead []
            [ Html.tr []
                [ Html.th [] [ Html.text "File" ]
                , Html.th [] [ Html.text "Rows" ]
                , Html.th [] [ Html.text "Size" ]
                , Html.th [] [ Html.text "Description" ]
                ]
            ]
        , Html.tbody [] (List.map (downloadRow ownPath) downloads)
        ]


downloadRow : String -> Download -> Html
downloadRow ownPath download =
    Html.tr []
        [ Html.td [] [ Html.a [ Html.attribute "href" (rootRelativeHref ownPath download.path) ] [ Html.text download.label ] ]
        , Html.td [] [ Html.text (String.fromInt download.rows) ]
        , Html.td [] [ Html.text (Data.humanBytes download.bytes) ]
        , Html.td [] [ Html.text download.description ]
        ]


{-| A link from `ownPath` (a page's own site-root-relative path, e.g.
`"agent-accessibility/index.html"`) to `targetPath` (a download's path, also
relative to the site root). Counted from `ownPath` itself rather than
hardcoded, so a page that ever moved to a different depth would carry a
correct link without anyone having to remember to update a `"../"` literal
by hand.
-}
rootRelativeHref : String -> String -> String
rootRelativeHref ownPath targetPath =
    String.concat [ String.repeat (depthOf ownPath) "../", targetPath ]


{-| How many directories deep `path` sits below the site root — the number
of `"/"` separators in it, since the final segment is always the file name
itself rather than a directory.
-}
depthOf : String -> Int
depthOf path =
    List.length (String.split "/" path) - 1



-- The historical index: three years of quarterly readings from Common
-- Crawl's archive, over its own panel and its own page.


historyPage : Flags -> Page
historyPage flags =
    let
        history =
            flags.history

        path =
            "agent-accessibility-history/index.html"
    in
    { path = path
    , content =
        Html.document
            { title = history.title
            , description = history.question
            , head = [ stylesheet ]
            , body =
                List.concat
                    [ [ pageHeader { title = history.title, subtitle = Just history.question, homeHref = "../index.html" }
                      , Html.main_ []
                            (List.concat
                                [ historyHeroSection history
                                , Chart.view { cadence = "quarterly" } history.prints history.series
                                , [ Html.section [ Html.attribute "class" "history" ]
                                        [ Html.h2 [] [ Html.text "Every published period" ]
                                        , historyTable history
                                        ]
                                  , howItIsReadSection
                                  , panelSection history.panel
                                  , coverageSection history.series
                                  , whyFinalSection
                                  , crawlsSection history
                                  ]
                                , supersededSection history.superseded history.prints
                                , downloadsSection path (Data.downloadsFor history.id flags.downloads)
                                ]
                            )
                      ]
                    , [ siteFooter ]
                    ]
            }
    }


historyHeroSection : History -> List Html
historyHeroSection history =
    case Data.latestPrint history.prints of
        Nothing ->
            [ Html.p [] [ Html.text "No historical reading has been published yet." ] ]

        Just latest ->
            List.concat
                [ provisionalBadge latest
                , [ Html.section [ Html.attribute "class" "headline" ]
                        [ Html.p [ Html.attribute "class" "headline-value" ] [ Html.text (Data.formatPercent latest.value) ]
                        , Html.p [ Html.attribute "class" "headline-caption" ]
                            [ Html.text
                                (String.concat
                                    [ "of "
                                    , latest.denominator
                                    , " conclusive domains in the panel named at least one AI crawler in robots.txt and disallowed it, as read from Common Crawl's "
                                    , crawlNameFor history.crawls latest.period
                                    , " archive."
                                    ]
                                )
                            ]
                        , Html.p [ Html.attribute "class" "meta" ]
                            [ Html.text
                                (String.concat
                                    [ "Coverage: "
                                    , Data.formatPercent latest.coverage
                                    , " of the panel had a conclusive reading for this period."
                                    ]
                                )
                            ]
                        ]
                  ]
                ]


{-| The human name Common Crawl gave the crawl that stands for one period, or
the bare period string if none is on record.
-}
crawlNameFor : List Crawl -> String -> String
crawlNameFor crawls period =
    crawls
        |> List.filter (\crawl -> crawl.period == period)
        |> List.head
        |> Maybe.map .name
        |> Maybe.withDefault period


historyTable : History -> Html
historyTable history =
    Html.table [ Html.attribute "class" "prints" ]
        [ Html.thead []
            [ Html.tr []
                [ Html.th [] [ Html.text "Period" ]
                , Html.th [] [ Html.text "Crawl" ]
                , Html.th [] [ Html.text "Targeted" ]
                , Html.th [] [ Html.text "Change" ]
                , Html.th [] [ Html.text "Conclusive domains" ]
                , Html.th [] [ Html.text "Coverage" ]
                ]
            ]
        , Html.tbody [] (List.map (historyTableRow history) (List.reverse history.prints))
        ]


historyTableRow : History -> Row -> Html
historyTableRow history row =
    Html.tr []
        [ Html.td [] [ Html.text row.period ]
        , Html.td [] [ Html.text (crawlNameFor history.crawls row.period) ]
        , Html.td [] [ Html.text (Data.formatPercent row.value) ]
        , Html.td [] [ Html.text (changeSince history.series row.period) ]
        , Html.td [] [ Html.text row.denominator ]
        , Html.td [] [ Html.text (Data.formatPercent row.coverage) ]
        ]


{-| The change from the previous reading, for the period's row in the
`change_since_previous` series, or blank for a period with none — the first
period in the series has no reading before it to compare against.
-}
changeSince : List Row -> String -> String
changeSince series period =
    Data.findBySeriesAndPeriod "change_since_previous" period series
        |> Maybe.map (\row -> signedChange (rowValue row))
        |> Maybe.withDefault ""


{-| `Data.formatFixed2`, but with an explicit "+" on positive values — in a
column with mixed signs, an unsigned positive is indistinguishable from a
sign that was simply left off. Negative values already carry their own "-"
from `formatFixed2`. Whether a value counts as positive is judged after the
same rounding `formatFixed2` applies, so a value that rounds to zero is
shown bare rather than as "+0.00".
-}
signedChange : Float -> String
signedChange value =
    case round (value * 100) > 0 of
        True ->
            String.concat [ "+", Data.formatFixed2 value ]

        False ->
            Data.formatFixed2 value


howItIsReadSection : Html
howItIsReadSection =
    Html.section []
        [ Html.h2 [] [ Html.text "How it is read" ]
        , Html.p []
            [ Html.text "This index reads the "
            , Html.code [] [ Html.text "robots.txt" ]
            , Html.text " that Common Crawl captured at the time, rather than anything our own crawler fetched, so it can reach back to before this project existed."
            ]
        , Html.p []
            [ Html.text "It is parsed by the same parser as the live index, so the two indices differ in how evidence is gathered and not at all in how it is read." ]
        ]


panelSection : HistoryPanel -> Html
panelSection panel =
    Html.section []
        [ Html.h2 [] [ Html.text "The panel" ]
        , Html.p []
            (List.concat
                [ [ Html.text
                        (String.concat
                            [ String.fromInt panel.size
                            , " domains: "
                            , panel.construction.rule
                            , ", "
                            ]
                        )
                  ]
                , List.intersperse (Html.text " and ") (List.map endpointLink panel.endpoints)
                , [ Html.text "." ]
                ]
            )
        , Html.p []
            [ Html.text
                (String.concat [ "Membership is fixed across the span: ", panel.construction.churn, "." ])
            ]
        , Html.p [ Html.attribute "class" "meta" ]
            [ Html.text (sentence panel.construction.knownBias) ]
        ]


endpointLink : CrawlEndpoint -> Html
endpointLink endpoint =
    Html.a
        [ Html.attribute "href" (String.concat [ "https://tranco-list.eu/list/", endpoint.trancoListId ]) ]
        [ Html.text (String.concat [ endpoint.trancoListId, " (", endpoint.date, ")" ]) ]


coverageSection : List Row -> Html
coverageSection series =
    Html.section []
        [ Html.h2 [] [ Html.text "Coverage" ]
        , Html.p []
            [ Html.text "Common Crawl did not capture a robots.txt for every panel domain in every crawl, so each period publishes the share it could read. "
            , Html.text (coverageRangeSentence series)
            ]
        , Html.p [] [ Html.text "Domains it could not read are excluded from the rate rather than assumed permissive." ]
        ]


coverageRangeSentence : List Row -> String
coverageRangeSentence series =
    case coverageRange series of
        Nothing ->
            "No coverage figures have been published yet."

        Just ( lowest, highest ) ->
            String.concat
                [ "Coverage ranges from "
                , Data.formatFixed2 lowest
                , "% to "
                , Data.formatFixed2 highest
                , "% across the published periods."
                ]


coverageRange : List Row -> Maybe ( Float, Float )
coverageRange series =
    let
        values =
            series
                |> List.filter (\row -> row.seriesId == Just "coverage")
                |> List.filterMap (\row -> String.toFloat row.value)
    in
    Maybe.map2 Tuple.pair (List.minimum values) (List.maximum values)


whyFinalSection : Html
whyFinalSection =
    Html.section []
        [ Html.h2 [] [ Html.text "Why these figures are final" ]
        , Html.p []
            [ Html.text "The live index marks a print provisional when coverage is low, because more evidence can still arrive inside its collection window. Common Crawl's archive is closed, so a historical reading can never be restated on coverage grounds and is final the moment it is computed. Coverage is published per period instead." ]
        ]


crawlsSection : History -> Html
crawlsSection history =
    Html.section []
        [ Html.h2 [] [ Html.text "Which crawls" ]
        , Html.p [] [ Html.text history.selection ]
        , Html.table []
            [ Html.thead []
                [ Html.tr []
                    [ Html.th [] [ Html.text "Crawl" ]
                    , Html.th [] [ Html.text "Name" ]
                    , Html.th [] [ Html.text "Period" ]
                    ]
                ]
            , Html.tbody [] (List.map crawlRow history.crawls)
            ]
        ]


crawlRow : Crawl -> Html
crawlRow crawl =
    Html.tr []
        [ Html.td [] [ Html.text crawl.crawl ]
        , Html.td [] [ Html.text crawl.name ]
        , Html.td [] [ Html.text crawl.period ]
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
                        , Html.p []
                            [ Html.text "The ledgers themselves are published as CSV in "
                            , Html.a [ Html.attribute "href" "../agent-accessibility/index.html" ] [ Html.text "the live index's downloads section" ]
                            , Html.text "."
                            ]
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
                        , Html.p [ Html.attribute "class" "meta" ] [ Html.text (sentence flags.panel.qualification.knownBias) ]
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



-- The crawler's own about page.


crawlerPage : Flags -> Page
crawlerPage flags =
    { path = "about/crawler/index.html"
    , content =
        Html.document
            { title = "The Tallyhouse crawler"
            , description = "What TallyhouseIndexBot fetches, how often, and how to ask it to stop."
            , head = [ stylesheet ]
            , body =
                [ pageHeader { title = "The Tallyhouse crawler", subtitle = Nothing, homeHref = "../../index.html" }
                , Html.main_ []
                    [ Html.section []
                        [ Html.h2 [] [ Html.text "What it is" ]
                        , Html.p []
                            [ Html.text "TallyhouseIndexBot is the crawler behind Tallyhouse, an index of how many of the most popular websites tell AI crawlers to stay out. It identifies itself as "
                            , Html.code [] [ Html.text flags.crawler.userAgent ]
                            , Html.text " and it does not pretend to be anything else."
                            ]
                        ]
                    , Html.section []
                        [ Html.h2 [] [ Html.text "What it fetches" ]
                        , Html.p []
                            [ Html.text "It requests exactly one file from your site: "
                            , Html.code [] [ Html.text "/robots.txt" ]
                            , Html.text ". It never requests any other page, never follows links, and never downloads images, scripts or stylesheets. If the apex domain does not answer it tries the "
                            , Html.code [] [ Html.text "www." ]
                            , Html.text " host, and if HTTPS does not answer it tries HTTP. That is the whole of its behaviour."
                            ]
                        , Html.p []
                            [ Html.text
                                (String.concat
                                    [ "It fetches once per week, at most three attempts with backoff if a request fails, and reads at most 512 KB of the file. Across the whole panel of "
                                    , String.fromInt flags.panel.size
                                    , " sites it holds no more than eight connections open at a time, so the load on any one site is a single small request a week."
                                    ]
                                )
                            ]
                        ]
                    , Html.section []
                        [ Html.h2 [] [ Html.text "What it will not do" ]
                        , Html.p []
                            [ Html.text "It does not attempt to look like a browser. It sends its own user-agent, makes no effort to match a browser's TLS or HTTP fingerprint, and does not run JavaScript." ]
                        , Html.p []
                            [ Html.text "It never tries to get past an anti-automation challenge. If a site answers with a challenge instead of the file, Tallyhouse records that it could not read the policy and moves on. Those sites are published as an \"unreadable\" figure rather than guessed at, because a site that would not show us its robots.txt has not told us anything about its policy either way." ]
                        ]
                    , verifySection flags.crawler
                    , Html.section []
                        [ Html.h2 [] [ Html.text "Asking it to stop" ]
                        , Html.p []
                            [ Html.text "Under RFC 9309 a crawler is always allowed to fetch "
                            , Html.code [] [ Html.text "/robots.txt" ]
                            , Html.text " itself — otherwise no crawler could ever learn the rules — so a "
                            , Html.code [] [ Html.text "Disallow" ]
                            , Html.text " rule cannot be the way to turn this one off. If you would rather your site were not in the panel, open an issue at "
                            , Html.a [ Html.attribute "href" "https://github.com/allanderek/tallyhouse/issues" ] [ Html.text "the project repository" ]
                            , Html.text " and it will be removed. Each removal is recorded in "
                            , Html.code [] [ Html.text "data/panel/removals.json" ]
                            , Html.text " with its reason and the week it takes effect from. The date matters: the panel is the denominator of every published figure, so a removal applies from a future week rather than reaching back and quietly restating numbers that have already been published. From that week the site is no longer requested at all, and it leaves the denominator rather than counting as a week we failed to read it."
                            ]
                        ]
                    , Html.section []
                        [ Html.h2 [] [ Html.text "Why it exists" ]
                        , Html.p []
                            [ Html.text "Tallyhouse publishes what sites ask of AI crawlers, weekly, from a committed ledger that anyone can re-derive. Reading robots.txt is the only way to learn what a site asks, and asking is the only thing this crawler does." ]
                        , Html.p []
                            [ Html.a [ Html.attribute "href" "../index.html" ] [ Html.text "More about how the index is built" ]
                            , Html.text "."
                            ]
                        ]
                    ]
                , siteFooter
                ]
            }
    }


{-| The section a bot-verification reviewer actually needs: the token and
user-agent this crawler claims, the fixed addresses that back the claim, and
the plain statement that anything else claiming this user-agent is an
impostor. `flags.crawler.userAgent` is read from the same flags field the
"What it is" section above draws from, so there is one source of truth for
the string rather than two copies that could drift apart.
-}
verifySection : Crawler -> Html
verifySection crawler =
    Html.section []
        (List.concat
            [ [ Html.h2 [] [ Html.text "How to verify it is us" ]
              , Html.p []
                    [ Html.text "This crawler is registered under the token "
                    , Html.text crawler.token
                    , Html.text ", and every request it makes carries the user-agent "
                    , Html.code [] [ Html.text crawler.userAgent ]
                    , Html.text "."
                    ]
              ]
            , egressParagraphs crawler.prefixes
            , [ Html.p []
                    [ Html.text "A request claiming this user-agent from any other address is not ours." ]
              ]
            ]
        )


{-| The egress addresses, or an honest admission that there are none yet.
Rendering an empty `ul` or a link to an `ips.json` with nothing in it would
be worse than saying nothing: it would look like a published list when there
isn't one.
-}
egressParagraphs : List String -> List Html
egressParagraphs prefixes =
    case prefixes of
        [] ->
            [ Html.p [] [ Html.text "No address list is currently published." ] ]

        _ ->
            [ Html.p []
                [ Html.text "All requests originate from the following addresses:" ]
            , Html.ul [] (List.map prefixItem prefixes)
            , Html.p []
                [ Html.text "The same list is published in machine-readable form at "
                , Html.a [ Html.attribute "href" "ips.json" ] [ Html.text "ips.json" ]
                , Html.text "."
                ]
            ]


prefixItem : String -> Html
prefixItem prefix =
    Html.li [] [ Html.code [] [ Html.text prefix ] ]



-- The crawler's machine-readable egress IP list, for bot-verification
-- tooling. Google's `googlebot.json` established the de-facto shape this
-- follows: a top-level "prefixes" list of single-key objects, each keyed
-- "ipv4Prefix" or "ipv6Prefix". Built with `Json.Encode` rather than a
-- hand-written string so the file is always valid JSON, even if a prefix
-- ever contained a character that would need escaping.


crawlerIpsPage : Flags -> Page
crawlerIpsPage flags =
    { path = "about/crawler/ips.json"
    , content = Encode.encode 2 (encodeIpsDocument flags.crawler.prefixes)
    }


encodeIpsDocument : List String -> Encode.Value
encodeIpsDocument prefixes =
    Encode.object
        [ ( "prefixes", Encode.list encodePrefix prefixes ) ]


{-| IPv6 CIDR notation always contains a `:`; IPv4 never does. That is
sufficient to tell them apart without a dedicated address-parsing library,
which this project's `elm.json` does not depend on.
-}
encodePrefix : String -> Encode.Value
encodePrefix prefix =
    case String.contains ":" prefix of
        True ->
            Encode.object [ ( "ipv6Prefix", Encode.string prefix ) ]

        False ->
            Encode.object [ ( "ipv4Prefix", Encode.string prefix ) ]



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
                    [ Html.td [] [ Html.a [ Html.attribute "href" (String.concat [ agent.slug, "/index.html" ]) ] [ Html.text agent.token ] ]
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
    { path = String.concat [ "agent-accessibility/agents/", agent.slug, "/index.html" ]
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
                                , agentHistorySection flags agent
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


{-| A token's own three-year line from the historical index, when it has
one. Omitted entirely, rather than shown with an empty chart, for a token
history predates or has simply never recorded — most of the 45 tracked
tokens are newer than the three-year span.
-}
agentHistorySection : Flags -> Agent -> List Html
agentHistorySection flags agent =
    let
        rows =
            Data.agentHistory agent.token flags.history.series
    in
    case rows of
        [] ->
            []

        _ ->
            [ Html.section [ Html.attribute "class" "agent-history" ]
                (List.concat
                    [ [ Html.h2 [] [ Html.text (String.concat [ agent.token, "'s three-year history" ]) ] ]
                    , Chart.viewOne { cadence = "quarterly", label = agent.token } rows
                    , [ firstBlockedSentence rows
                      , historyNotComparableCaution flags.history.panel
                      ]
                    ]
                )
            ]


{-| When this token was first named and disallowed by any site in the
historical panel, and its most recent reading — both read from the data
rather than assumed, so the sentence stays true whatever a future vintage
of the ledger says.
-}
firstBlockedSentence : List Row -> Html
firstBlockedSentence rows =
    case Data.latestPrint rows of
        Nothing ->
            Html.p [] [ Html.text "No historical reading has been published yet." ]

        Just latest ->
            Html.p [] [ Html.text (firstBlockedText (Data.firstBlockedPeriod rows) (Data.formatPercent latest.value)) ]


firstBlockedText : Maybe String -> String -> String
firstBlockedText maybeFirstBlocked latestValue =
    case maybeFirstBlocked of
        Nothing ->
            String.concat
                [ "No site in the historical panel has ever named and disallowed this token; its most recent reading is "
                , latestValue
                , "."
                ]

        Just period ->
            String.concat
                [ "A site in the historical panel first named and disallowed this token in "
                , period
                , "; its most recent reading is "
                , latestValue
                , "."
                ]


{-| This chart's panel is not the panel behind the stance table above it on
the same page: the live panel is a single dated snapshot, the historical
panel is a fixed set read across three years from Common Crawl's archive.
`notComparable` is the ledger's own account of that limit, read back rather
than restated here.
-}
historyNotComparableCaution : HistoryPanel -> Html
historyNotComparableCaution panel =
    Html.p [ Html.attribute "class" "meta" ]
        [ Html.text
            (String.concat
                [ "Note: this chart reads Common Crawl's own "
                , String.fromInt panel.size
                , "-domain historical panel, not the panel behind the stance table above — "
                , panel.construction.notComparable
                , "."
                ]
            )
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
