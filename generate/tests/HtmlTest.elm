module HtmlTest exposing (suite)

import Expect
import Html
import Test exposing (Test, describe, test)


suite : Test
suite =
    describe "Html"
        [ describe "escape"
            [ test "escapes ampersand" <|
                \_ ->
                    Html.escape "&"
                        |> Expect.equal "&amp;"
            , test "escapes less-than" <|
                \_ ->
                    Html.escape "<"
                        |> Expect.equal "&lt;"
            , test "escapes greater-than" <|
                \_ ->
                    Html.escape ">"
                        |> Expect.equal "&gt;"
            , test "escapes double quote" <|
                \_ ->
                    Html.escape "\""
                        |> Expect.equal "&quot;"
            , test "escapes single quote" <|
                \_ ->
                    Html.escape "'"
                        |> Expect.equal "&#39;"
            , test "does not double-escape an existing entity" <|
                \_ ->
                    Html.escape "&amp;"
                        |> Expect.equal "&amp;amp;"

            -- This looks surprising at first: escaping "&amp;" turns the
            -- "&" into "&amp;", giving "&amp;amp;", which is correct
            -- behaviour for `escape` applied to raw text that happens to
            -- contain a literal "&amp;" string. The real "no double
            -- escaping" guarantee is that `escape` is called exactly once
            -- per piece of text as it is rendered, never twice on the same
            -- string - which the next test checks end to end.
            , test "renders plain text containing an ampersand exactly once escaped" <|
                \_ ->
                    Html.text "Tom & Jerry"
                        |> Html.toString
                        |> Expect.equal "Tom &amp; Jerry"
            ]
        , describe "attribute escaping"
            [ test "escapes special characters in attribute values" <|
                \_ ->
                    Html.node "div" [ ( "title", "<script> & \"quotes\" & 'ticks'" ) ] []
                        |> Html.toString
                        |> Expect.equal "<div title=\"&lt;script&gt; &amp; &quot;quotes&quot; &amp; &#39;ticks&#39;\"></div>"
            ]
        , describe "hostile content"
            [ test "a hostile robots.txt body is inert inside a pre" <|
                \_ ->
                    Html.pre [] [ Html.text "</pre><script>alert('xss')</script> & \"quoted\"" ]
                        |> Html.toString
                        |> Expect.equal "<pre>&lt;/pre&gt;&lt;script&gt;alert(&#39;xss&#39;)&lt;/script&gt; &amp; &quot;quoted&quot;</pre>"
            ]
        , describe "raw"
            [ test "passes content through unescaped" <|
                \_ ->
                    Html.raw "<svg><circle/></svg>"
                        |> Html.toString
                        |> Expect.equal "<svg><circle/></svg>"
            ]
        , describe "void elements"
            [ test "meta has no closing tag" <|
                \_ ->
                    Html.node "meta" [ ( "charset", "utf-8" ) ] []
                        |> Html.toString
                        |> Expect.equal "<meta charset=\"utf-8\">"
            , test "br has no closing tag and ignores children" <|
                \_ ->
                    Html.node "br" [] [ Html.text "ignored" ]
                        |> Html.toString
                        |> Expect.equal "<br>"
            , test "a non-void element does get a closing tag" <|
                \_ ->
                    Html.div [] []
                        |> Html.toString
                        |> Expect.equal "<div></div>"
            ]
        , describe "nesting and attribute order"
            [ test "children render in order" <|
                \_ ->
                    Html.ul []
                        [ Html.li [] [ Html.text "one" ]
                        , Html.li [] [ Html.text "two" ]
                        ]
                        |> Html.toString
                        |> Expect.equal "<ul><li>one</li><li>two</li></ul>"
            , test "attributes render in the exact order given" <|
                \_ ->
                    Html.node "a" [ ( "href", "/x" ), ( "class", "link" ), ( "id", "y" ) ] [ Html.text "x" ]
                        |> Html.toString
                        |> Expect.equal "<a href=\"/x\" class=\"link\" id=\"y\">x</a>"
            , test "deep nesting renders correctly" <|
                \_ ->
                    Html.div [ ( "class", "outer" ) ]
                        [ Html.section []
                            [ Html.h1 [] [ Html.text "Title" ]
                            , Html.p [] [ Html.text "Body" ]
                            ]
                        ]
                        |> Html.toString
                        |> Expect.equal "<div class=\"outer\"><section><h1>Title</h1><p>Body</p></section></div>"
            ]
        , describe "document"
            [ test "produces a full HTML5 document with escaped title and description" <|
                \_ ->
                    Html.document
                        { title = "A & B"
                        , description = "<desc>"
                        , head = []
                        , body = [ Html.p [] [ Html.text "hi" ] ]
                        }
                        |> Expect.equal
                            (String.concat
                                [ "<!DOCTYPE html>\n"
                                , "<html lang=\"en\">\n"
                                , "<head>\n"
                                , "<meta charset=\"utf-8\">\n"
                                , "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
                                , "<meta name=\"description\" content=\"&lt;desc&gt;\">\n"
                                , "<title>A &amp; B</title>\n"
                                , "</head>\n"
                                , "<body>\n"
                                , "<p>hi</p>"
                                , "\n</body>\n"
                                , "</html>\n"
                                ]
                            )
            , test "an empty head still produces a valid document with charset and viewport intact" <|
                \_ ->
                    Html.document
                        { title = "T"
                        , description = "D"
                        , head = []
                        , body = []
                        }
                        |> Expect.equal
                            (String.concat
                                [ "<!DOCTYPE html>\n"
                                , "<html lang=\"en\">\n"
                                , "<head>\n"
                                , "<meta charset=\"utf-8\">\n"
                                , "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
                                , "<meta name=\"description\" content=\"D\">\n"
                                , "<title>T</title>\n"
                                , "</head>\n"
                                , "<body>\n"
                                , "\n</body>\n"
                                , "</html>\n"
                                ]
                            )
            , test "renders head content after the charset and viewport meta tags and before description and title, never inside body" <|
                \_ ->
                    Html.document
                        { title = "A & B"
                        , description = "<desc>"
                        , head = [ Html.node "style" [] [ Html.raw "body{color:blue}" ] ]
                        , body = [ Html.p [] [ Html.text "hi" ] ]
                        }
                        |> Expect.equal
                            (String.concat
                                [ "<!DOCTYPE html>\n"
                                , "<html lang=\"en\">\n"
                                , "<head>\n"
                                , "<meta charset=\"utf-8\">\n"
                                , "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
                                , "<style>body{color:blue}</style>"
                                , "<meta name=\"description\" content=\"&lt;desc&gt;\">\n"
                                , "<title>A &amp; B</title>\n"
                                , "</head>\n"
                                , "<body>\n"
                                , "<p>hi</p>"
                                , "\n</body>\n"
                                , "</html>\n"
                                ]
                            )
            , test "escapes Html.text in head content but passes Html.raw through unescaped, so an inline stylesheet's selectors are not mangled" <|
                \_ ->
                    Html.document
                        { title = "T"
                        , description = "D"
                        , head =
                            [ Html.node "style" [] [ Html.raw "a>b{color:red}" ]
                            , Html.node "script" [] [ Html.text "1 < 2" ]
                            ]
                        , body = []
                        }
                        |> Expect.equal
                            (String.concat
                                [ "<!DOCTYPE html>\n"
                                , "<html lang=\"en\">\n"
                                , "<head>\n"
                                , "<meta charset=\"utf-8\">\n"
                                , "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
                                , "<style>a>b{color:red}</style>"
                                , "<script>1 &lt; 2</script>"
                                , "<meta name=\"description\" content=\"D\">\n"
                                , "<title>T</title>\n"
                                , "</head>\n"
                                , "<body>\n"
                                , "\n</body>\n"
                                , "</html>\n"
                                ]
                            )
            ]
        ]
