# IIXII Store catalogue automation

Copy the `.github` folder from this package into the public `IIXII-L192/IIXIIStore` repository.

Place the separately supplied `registry.json` at:

```text
catalog/registry.json
```

Create these repository labels if they do not already exist:

- `app-submission`
- `publish-app`

The workflow creates/updates its other result labels automatically.

## Publishing an app

1. Open an issue using the **Add an app** issue form.
2. Review all fields and URLs.
3. Add the `publish-app` label.
4. The workflow validates the issue, inserts the app into `catalog/registry.json`, commits the change, comments on the issue, and closes it.

Alternatively, use **Actions → Publish app from issue → Run workflow** and enter the issue number.

`screenshot_urls` is always a JSON array and supports zero, one, or any number of image URLs.
