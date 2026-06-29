# LINE Notify Setup Guide

If your Sentry system is detecting falls but not sending LINE alerts, it is likely because you have reached the 200-message monthly limit on the LINE free tier, or your tokens have expired. 

Follow this guide to create a new LINE Channel and update your tokens.

## Step 1: Access the Correct Website
**⚠️ IMPORTANT:** Do not use the *LINE Official Account Manager* (`manager.line.biz`). The tokens you need are located in the **LINE Developers Console**.

1. Go to [LINE Developers Console](https://developers.line.biz/console/).
2. Log in using your personal LINE account credentials.

## Step 2: Create a Provider & Channel
1. Click **Create a new provider** (or select an existing one if you prefer). Name it something like `Sentry IoT`.
2. Inside the provider, click **Create a new channel**.
3. Select **Messaging API**.
4. Fill in the required details:
   - **Channel name**: e.g., `Sentry Alerts`
   - **Channel description**: `Fall detection alerts`
   - **Category**: `Health/Fitness`
   - Agree to the Terms of Use and click **Create**.

## Step 3: Get the Channel Access Token
1. In your new channel, click on the **Messaging API** tab (the middle tab).
2. Scroll to the very bottom to the section labeled **Channel access token (long-lived)**.
3. Click the **Issue** button.
4. Copy the long string of text. This is your `line_channel_access_token`.

## Step 4: Get Your User ID
1. Switch to the **Basic settings** tab (the first tab).
2. Scroll all the way to the bottom.
3. Look for the section labeled **Your user ID** (the string usually starts with a `U`). 
4. Copy this string. This is your `line_user_id`.
*(Note: Do not use the "Basic ID" that starts with an `@`. That is the Bot's ID, not your personal ID).*

## Step 5: Add the Bot as a Friend
**🚨 CRITICAL STEP:** If you do not add the bot as a friend on your phone, it will not be able to send you messages!
1. Go back to the **Messaging API** tab.
2. At the top of the page, you will see a QR code.
3. Scan this QR code using the LINE app on your phone and add the bot as a friend.

## Step 6: Update Sentry Configuration
Now that you have your tokens, you need to update the Sentry brain.

1. SSH into your Raspberry Pi (or open the Sentry source code).
2. Open the `config.json` file located in the root of the project (`/home/ohmpatumwan/Sentry/config.json`).
3. Update the `notifications` section with your new tokens:
   ```json
   "notifications": {
       "line_channel_access_token": "YOUR_NEW_LONG_CHANNEL_TOKEN_HERE",
       "line_user_id": "YOUR_NEW_U_USER_ID_HERE"
   }
   ```
4. Save the file.
5. Restart the Sentry background service to load the new tokens:
   ```bash
   sudo systemctl restart sentry
   ```

Your limits are now reset, and fall alerts should instantly begin working again!
