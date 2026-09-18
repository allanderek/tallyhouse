module Html exposing
    ( Attribute
    , Html(..)
    , a
    , attribute
    , code
    , div
    , document
    , escape
    , footer
    , h1
    , h2
    , h3
    , header
    , li
    , main_
    , nav
    , node
    , p
    , pre
    , raw
    , section
    , span
    , table
    , tbody
    , td
    , text
    , th
    , thead
    , time
    , toString
    , tr
    , ul
    )

{-| A minimal HTML abstract syntax tree and renderer.

There is no DOM available where this program runs, so `elm/html` is not an
option: this module exists to build up a tree of markup and render it to a
plain `String`.

The renderer is written defensively. Most of the content flowing through it
originates from other people's servers (fetched `robots.txt` files, page
titles, and so on) and must never be able to inject markup of its own.

-}


{-| The HTML AST.

  - `Node tag attributes children` is an element.
  - `Text content` is escaped text content.
  - `Raw content` is inserted into the output verbatim, with no escaping at
    all. Use it only for markup this program generated itself (for example
    inline SVG), never for content that came from an external source.

-}
type Html
    = Node String (List Attribute) (List Html)
    | Text String
    | Raw String


{-| An attribute name/value pair, e.g. `( "class", "tally-table" )`.
-}
type alias Attribute =
    ( String, String )


{-| Build an element with the given tag name, attributes and children.
-}
node : String -> List Attribute -> List Html -> Html
node =
    Node


{-| Escaped text content.
-}
text : String -> Html
text =
    Text


{-| Markup inserted verbatim, with no escaping. See the warning on the
`Html` type above.
-}
raw : String -> Html
raw =
    Raw


{-| Build an `Attribute` from a name and a value.
-}
attribute : String -> String -> Attribute
attribute key value =
    ( key, value )


{-| Escape the five characters that matter for safely embedding text inside
HTML: `&`, `<`, `>`, `"` and `'`.

`&` is replaced first. If it were replaced later, the entities introduced by
the other replacements (`&lt;`, `&quot;`, ...) would themselves be escaped
again, corrupting the output.

-}
escape : String -> String
escape input =
    input
        |> String.replace "&" "&amp;"
        |> String.replace "<" "&lt;"
        |> String.replace ">" "&gt;"
        |> String.replace "\"" "&quot;"
        |> String.replace "'" "&#39;"


{-| Tags that never have a closing tag and never have children, per the
HTML5 void elements list (restricted here to the ones this project uses).
A `Node` built with one of these tags renders as `<tag ...>` with no
`</tag>`, and any children passed to it are silently ignored.
-}
voidElements : List String
voidElements =
    [ "meta", "link", "br", "img", "input", "hr" ]


isVoidElement : String -> Bool
isVoidElement tag =
    List.member tag voidElements


{-| Render a tree of `Html` to a `String`.
-}
toString : Html -> String
toString html =
    case html of
        Text content ->
            escape content

        Raw content ->
            content

        Node tag attributes children ->
            renderNode tag attributes children


renderNode : String -> List Attribute -> List Html -> String
renderNode tag attributes children =
    let
        openTag =
            String.concat [ "<", tag, renderAttributes attributes, ">" ]
    in
    case isVoidElement tag of
        True ->
            openTag

        False ->
            String.concat
                [ openTag
                , String.concat (List.map toString children)
                , "</"
                , tag
                , ">"
                ]


renderAttributes : List Attribute -> String
renderAttributes attributes =
    attributes
        |> List.map renderAttribute
        |> List.map (String.append " ")
        |> String.concat


renderAttribute : Attribute -> String
renderAttribute ( key, value ) =
    String.concat [ key, "=\"", escape value, "\"" ]


{-| Render a complete, minimal HTML5 document: doctype, a `utf-8` charset
meta tag, a responsive viewport meta tag, a `<title>`, a `description` meta
tag, and the given body. No external assets (stylesheets, scripts, fonts)
are referenced.
-}
document : { title : String, description : String, body : List Html } -> String
document config =
    String.concat
        [ "<!DOCTYPE html>\n"
        , "<html lang=\"en\">\n"
        , "<head>\n"
        , "<meta charset=\"utf-8\">\n"
        , "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        , "<meta name=\"description\" content=\""
        , escape config.description
        , "\">\n"
        , "<title>"
        , escape config.title
        , "</title>\n"
        , "</head>\n"
        , "<body>\n"
        , String.concat (List.map toString config.body)
        , "\n</body>\n"
        , "</html>\n"
        ]



-- Convenience constructors for the tags this site needs.


div : List Attribute -> List Html -> Html
div =
    node "div"


p : List Attribute -> List Html -> Html
p =
    node "p"


h1 : List Attribute -> List Html -> Html
h1 =
    node "h1"


h2 : List Attribute -> List Html -> Html
h2 =
    node "h2"


h3 : List Attribute -> List Html -> Html
h3 =
    node "h3"


ul : List Attribute -> List Html -> Html
ul =
    node "ul"


li : List Attribute -> List Html -> Html
li =
    node "li"


table : List Attribute -> List Html -> Html
table =
    node "table"


thead : List Attribute -> List Html -> Html
thead =
    node "thead"


tbody : List Attribute -> List Html -> Html
tbody =
    node "tbody"


tr : List Attribute -> List Html -> Html
tr =
    node "tr"


th : List Attribute -> List Html -> Html
th =
    node "th"


td : List Attribute -> List Html -> Html
td =
    node "td"


a : List Attribute -> List Html -> Html
a =
    node "a"


span : List Attribute -> List Html -> Html
span =
    node "span"


code : List Attribute -> List Html -> Html
code =
    node "code"


pre : List Attribute -> List Html -> Html
pre =
    node "pre"


section : List Attribute -> List Html -> Html
section =
    node "section"


main_ : List Attribute -> List Html -> Html
main_ =
    node "main"


header : List Attribute -> List Html -> Html
header =
    node "header"


footer : List Attribute -> List Html -> Html
footer =
    node "footer"


nav : List Attribute -> List Html -> Html
nav =
    node "nav"


time : List Attribute -> List Html -> Html
time =
    node "time"
